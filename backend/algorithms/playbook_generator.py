"""AI-powered recovery playbook generation using Claude API + Qdrant RAG + topology context."""
import json
from datetime import datetime
from uuid import uuid4

import anthropic
import structlog

from models.features import PlaybookStep, RecoveryPlaybook

log = structlog.get_logger()

# In-memory playbook cache: node_id → RecoveryPlaybook
_playbook_cache: dict[str, RecoveryPlaybook] = {}

_STATIC_STEPS_BY_STRATEGY = {
    "replica_fallback": [
        PlaybookStep(step=1, action="Verify failure is confirmed and not a monitoring flap", owner="on-call", estimated_minutes=2),
        PlaybookStep(step=2, action="Promote healthy replica to primary", owner="DBA", estimated_minutes=5, commands=["aws rds failover-db-cluster --db-cluster-identifier <id>"]),
        PlaybookStep(step=3, action="Update connection strings in downstream services", owner="SRE", estimated_minutes=10),
        PlaybookStep(step=4, action="Validate downstream service health and reconnection", owner="on-call", estimated_minutes=5),
        PlaybookStep(step=5, action="Document incident and update postmortem", owner="on-call", estimated_minutes=15),
    ],
    "multi_az": [
        PlaybookStep(step=1, action="Confirm AZ-level failure via AWS Health Dashboard", owner="on-call", estimated_minutes=2),
        PlaybookStep(step=2, action="Trigger Multi-AZ failover (automatic or manual)", owner="SRE", estimated_minutes=3, commands=["aws rds reboot-db-instance --db-instance-identifier <id> --force-failover"]),
        PlaybookStep(step=3, action="Verify DNS propagation to secondary AZ endpoint", owner="SRE", estimated_minutes=5),
        PlaybookStep(step=4, action="Check application connection pool reconnection", owner="on-call", estimated_minutes=5),
        PlaybookStep(step=5, action="Monitor for 15 minutes before declaring stable", owner="on-call", estimated_minutes=15),
    ],
    "stateless": [
        PlaybookStep(step=1, action="Terminate unhealthy instance(s)", owner="on-call", estimated_minutes=1, commands=["aws ec2 terminate-instances --instance-ids <id>"]),
        PlaybookStep(step=2, action="Auto-scaling group launches replacement instance", owner="SRE", estimated_minutes=3),
        PlaybookStep(step=3, action="Verify new instance passes health checks", owner="on-call", estimated_minutes=5),
        PlaybookStep(step=4, action="Confirm load balancer routes traffic to new instance", owner="on-call", estimated_minutes=2),
    ],
    "backup_fallback": [
        PlaybookStep(step=1, action="Identify latest valid backup within RPO window", owner="DBA", estimated_minutes=5),
        PlaybookStep(step=2, action="Initiate restore from backup to standby instance", owner="DBA", estimated_minutes=30, commands=["aws rds restore-db-instance-from-db-snapshot"]),
        PlaybookStep(step=3, action="Validate data integrity after restore", owner="DBA", estimated_minutes=10),
        PlaybookStep(step=4, action="Switch traffic to restored instance", owner="SRE", estimated_minutes=5),
        PlaybookStep(step=5, action="Notify stakeholders of data loss window", owner="on-call", estimated_minutes=5),
        PlaybookStep(step=6, action="Document and post-mortem", owner="on-call", estimated_minutes=20),
    ],
    "generic": [
        PlaybookStep(step=1, action="Confirm failure alert is not a false positive", owner="on-call", estimated_minutes=2),
        PlaybookStep(step=2, action="Isolate failed component to stop blast radius growth", owner="SRE", estimated_minutes=5),
        PlaybookStep(step=3, action="Identify recovery path (replica, backup, redeploy)", owner="SRE", estimated_minutes=10),
        PlaybookStep(step=4, action="Execute recovery procedure", owner="SRE", estimated_minutes=20),
        PlaybookStep(step=5, action="Validate all downstream services recovered", owner="on-call", estimated_minutes=10),
        PlaybookStep(step=6, action="Update status page and notify stakeholders", owner="on-call", estimated_minutes=5),
        PlaybookStep(step=7, action="Conduct post-mortem within 48 hours", owner="on-call", estimated_minutes=60),
    ],
}

_SYSTEM_PROMPT = (
    "You are a senior SRE at a cloud-native company specializing in AWS disaster recovery. "
    "You generate precise, actionable runbooks grounded in the specific infrastructure context provided. "
    "Always respond with valid JSON only — no markdown, no code fences, no explanation."
)


def _build_claude_prompt(
    node: dict,
    downstream: list[dict],
    upstream: list[dict],
    doc_context: str,
) -> str:
    def _fmt_nodes(nodes: list[dict]) -> str:
        if not nodes:
            return "  (none)"
        return "\n".join(
            f"  - {n.get('name', n.get('id', '?'))} [{n.get('type', 'unknown')}]"
            for n in nodes[:12]
        )

    doc_section = (
        f"\n## Relevant DR Documentation\n{doc_context[:3000]}"
        if doc_context.strip()
        else ""
    )

    return f"""Generate a disaster recovery runbook for the following infrastructure failure.

## Failed Node
- Name: {node.get('name')}
- AWS Resource Type: {node.get('type')}
- Region: {node.get('region', 'us-east-1')}
- Recovery Strategy: {node.get('recovery_strategy', 'generic')}
- RTO Target: {node.get('rto_minutes', 60)} minutes
- RPO Target: {node.get('rpo_minutes', 15)} minutes

## Topology Impact
### Downstream Services (directly affected by this failure)
{_fmt_nodes(downstream)}

### Upstream Dependencies (services this node depends on)
{_fmt_nodes(upstream)}
{doc_section}

Return ONLY this JSON (no other text):
{{
  "summary": "One-sentence executive summary of the failure scenario and recovery approach",
  "steps": [
    {{
      "step": 1,
      "action": "Specific, concrete action with resource names where possible",
      "owner": "on-call|SRE|DBA|platform-team",
      "estimated_minutes": 5,
      "commands": ["aws cli or kubectl commands if applicable, empty array if none"]
    }}
  ]
}}

Generate 6-8 steps. Commands must reference the actual resource type ({node.get('type')}) and region ({node.get('region', 'us-east-1')}). Tailor every step to the {node.get('recovery_strategy', 'generic')} strategy."""


async def _call_claude(prompt: str, settings) -> str:
    """Call Claude API and return the raw text response."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def generate_playbook(
    node_id: str,
    neo4j,
    qdrant,
    settings,
    include_docs: bool = True,
    force_regenerate: bool = False,
) -> RecoveryPlaybook:
    """
    Generate AI-powered recovery playbook using Claude API.
    Context: Neo4j topology (node + upstream/downstream) + Qdrant RAG docs.
    Falls back to static steps if Claude is unavailable or not configured.
    """
    if not force_regenerate and node_id in _playbook_cache:
        log.info("playbook_cache_hit", node_id=node_id)
        return _playbook_cache[node_id]

    # ── 1. Fetch node details from Neo4j ──────────────────────────────
    rows = await neo4j.run(
        "MATCH (n:InfraNode {id: $id}) RETURN "
        "n.id AS id, n.name AS name, n.type AS type, "
        "n.recovery_strategy AS recovery_strategy, "
        "n.rto_minutes AS rto_minutes, n.rpo_minutes AS rpo_minutes, "
        "n.region AS region",
        {"id": node_id},
    )
    if not rows:
        raise ValueError(f"Node '{node_id}' not found")
    node = rows[0]

    # ── 2. Topology context: downstream + upstream ─────────────────────
    downstream = await neo4j.run(
        "MATCH (n {id: $id})-[]->(dep:InfraNode) "
        "RETURN dep.name AS name, dep.type AS type, dep.region AS region LIMIT 12",
        {"id": node_id},
    )
    upstream = await neo4j.run(
        "MATCH (src:InfraNode)-[]->(n {id: $id}) "
        "RETURN src.name AS name, src.type AS type, src.region AS region LIMIT 12",
        {"id": node_id},
    )

    # ── 3. Qdrant RAG documentation context ───────────────────────────
    doc_context = ""
    doc_refs: list[str] = []
    if include_docs:
        try:
            from parsers.docs import _embed
            query = (
                f"disaster recovery runbook {node.get('type', '')} "
                f"{node.get('recovery_strategy', '')} AWS"
            )
            vector = await _embed(query)
            docs = await qdrant.search(vector=vector, limit=4)
            if docs:
                doc_context = "\n---\n".join(
                    d["payload"].get("text", "") for d in docs
                )
                doc_refs = [
                    d["payload"].get("source_file", "")
                    for d in docs
                    if d.get("payload")
                ]
        except Exception as exc:
            log.warning("playbook_qdrant_search_failed", error=str(exc))

    # ── 4. Claude API generation ───────────────────────────────────────
    steps: list[PlaybookStep] = []
    summary = ""
    generation_source = "claude"
    llm_model = settings.anthropic_model

    use_claude = bool(settings.anthropic_api_key)

    if use_claude:
        try:
            prompt = _build_claude_prompt(node, downstream, upstream, doc_context)
            raw = await _call_claude(prompt, settings)

            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(raw[json_start:json_end])
                summary = parsed.get("summary", "")
                for s in parsed.get("steps", []):
                    steps.append(PlaybookStep(
                        step=s.get("step", len(steps) + 1),
                        action=s.get("action", ""),
                        owner=s.get("owner", "on-call"),
                        estimated_minutes=s.get("estimated_minutes"),
                        commands=s.get("commands", []),
                    ))
            log.info(
                "playbook_claude_success",
                node_id=node_id,
                model=llm_model,
                steps=len(steps),
            )
        except Exception as exc:
            log.warning(
                "playbook_claude_failed",
                node_id=node_id,
                error=str(exc) or type(exc).__name__,
            )
            use_claude = False

    # ── 5. Static fallback ─────────────────────────────────────────────
    if not use_claude or not steps:
        strategy = node.get("recovery_strategy", "generic") or "generic"
        steps = _STATIC_STEPS_BY_STRATEGY.get(strategy, _STATIC_STEPS_BY_STRATEGY["generic"])
        summary = (
            f"Static recovery runbook for {node.get('name', node_id)} "
            f"using {strategy} strategy."
            + (" Claude API unavailable." if use_claude else "")
        )
        generation_source = "static"
        llm_model = "none"

    playbook = RecoveryPlaybook(
        playbook_id=str(uuid4()),
        node_id=node_id,
        node_name=node.get("name", node_id),
        node_type=node.get("type", "unknown"),
        recovery_strategy=node.get("recovery_strategy", "generic") or "generic",
        rto_minutes=node.get("rto_minutes"),
        rpo_minutes=node.get("rpo_minutes"),
        generated_at=datetime.utcnow().isoformat(),
        summary=summary,
        steps=steps,
        doc_references=[r for r in doc_refs if r],
        llm_model=llm_model,
        generation_source=generation_source,
    )

    _playbook_cache[node_id] = playbook
    return playbook
