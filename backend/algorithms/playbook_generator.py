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

_STATIC_STEPS_BY_STRATEGY: dict[str, list[PlaybookStep]] = {
    "replica_fallback": [
        PlaybookStep(step=1, action="Verify failure is confirmed and not a monitoring flap", owner="on-call", estimated_minutes=2, risk_level="low", verification="Alert still firing after 2 minutes with 3+ data points", rollback="No rollback needed — observation only"),
        PlaybookStep(step=2, action="Promote healthy read replica to primary", owner="DBA", estimated_minutes=5, commands=["aws rds failover-db-cluster --db-cluster-identifier <cluster-id> --target-db-instance-identifier <replica-id>"], risk_level="high", verification="aws rds describe-db-instances shows new primary in 'available' state", rollback="Re-promote original primary if replica is corrupted or lagging"),
        PlaybookStep(step=3, action="Update connection strings in downstream services via config or service mesh", owner="SRE", estimated_minutes=10, commands=["kubectl set env deployment/<app> DB_HOST=<new-endpoint>", "aws ssm put-parameter --name /app/db_host --value <new-endpoint> --overwrite"], risk_level="medium", verification="Application logs show successful DB connections to new endpoint", rollback="Revert SSM parameter and redeploy with original endpoint"),
        PlaybookStep(step=4, action="Validate downstream service health and reconnection", owner="on-call", estimated_minutes=5, verification="All health checks green, error rate back to baseline", rollback="Escalate to platform team if health checks remain red"),
        PlaybookStep(step=5, action="Document incident timeline and open postmortem ticket", owner="on-call", estimated_minutes=15),
    ],
    "multi_az": [
        PlaybookStep(step=1, action="Confirm AZ-level failure via AWS Health Dashboard", owner="on-call", estimated_minutes=2, risk_level="low", verification="AWS Health Dashboard shows AZ event matching alert timing"),
        PlaybookStep(step=2, action="Trigger Multi-AZ failover", owner="SRE", estimated_minutes=3, commands=["aws rds reboot-db-instance --db-instance-identifier <id> --force-failover"], risk_level="high", verification="RDS console shows secondary AZ as new primary", rollback="Contact AWS Support if failover does not complete within 5 minutes"),
        PlaybookStep(step=3, action="Verify DNS propagation to secondary AZ endpoint", owner="SRE", estimated_minutes=5, commands=["nslookup <rds-endpoint>", "dig +short <rds-endpoint>"], risk_level="medium", verification="DNS resolves to IP in secondary AZ subnet range"),
        PlaybookStep(step=4, action="Check application connection pool reconnection", owner="on-call", estimated_minutes=5, verification="Application error rate drops to <0.1% within 2 minutes", rollback="Force connection pool drain: restart application pods"),
        PlaybookStep(step=5, action="Monitor for 15 minutes before declaring stable", owner="on-call", estimated_minutes=15),
    ],
    "stateless": [
        PlaybookStep(step=1, action="Terminate unhealthy instance(s) to trigger ASG replacement", owner="on-call", estimated_minutes=1, commands=["aws ec2 terminate-instances --instance-ids <id>"], risk_level="low", verification="ASG shows desired count = running count after replacement", rollback="If ASG fails to launch, check launch template and IAM role"),
        PlaybookStep(step=2, action="Verify ASG launches replacement instance in healthy AZ", owner="SRE", estimated_minutes=3, verification="New instance reaches 'InService' state in target group"),
        PlaybookStep(step=3, action="Confirm load balancer routes traffic to new instance", owner="on-call", estimated_minutes=2, commands=["aws elbv2 describe-target-health --target-group-arn <arn>"], verification="Target health shows 'healthy' for new instance"),
        PlaybookStep(step=4, action="Monitor error rate for 10 minutes", owner="on-call", estimated_minutes=10, verification="Error rate back to baseline, latency p95 within normal range"),
    ],
    "backup_fallback": [
        PlaybookStep(step=1, action="Identify latest valid backup within RPO window", owner="DBA", estimated_minutes=5, commands=["aws rds describe-db-snapshots --db-instance-identifier <id> --query 'sort_by(DBSnapshots,&SnapshotCreateTime)[-1]'"], risk_level="low", verification="Snapshot creation time is within RPO window"),
        PlaybookStep(step=2, action="Initiate restore from snapshot to standby instance", owner="DBA", estimated_minutes=30, commands=["aws rds restore-db-instance-from-db-snapshot --db-instance-identifier <new-id> --db-snapshot-identifier <snapshot-id>"], risk_level="high", verification="New instance reaches 'available' state", rollback="Delete failed restore attempt and retry with earlier snapshot"),
        PlaybookStep(step=3, action="Validate data integrity after restore", owner="DBA", estimated_minutes=10, commands=["psql -h <new-endpoint> -U admin -c 'SELECT COUNT(*) FROM critical_table'"], risk_level="medium", verification="Row counts match last known good state"),
        PlaybookStep(step=4, action="Switch traffic to restored instance", owner="SRE", estimated_minutes=5, risk_level="high", rollback="Switch back to original endpoint if data validation fails"),
        PlaybookStep(step=5, action="Notify stakeholders of confirmed data loss window", owner="on-call", estimated_minutes=5),
        PlaybookStep(step=6, action="Document and schedule post-mortem", owner="on-call", estimated_minutes=20),
    ],
    "generic": [
        PlaybookStep(step=1, action="Confirm failure alert is not a false positive", owner="on-call", estimated_minutes=2, risk_level="low"),
        PlaybookStep(step=2, action="Isolate failed component to stop blast radius growth", owner="SRE", estimated_minutes=5, risk_level="medium", rollback="Re-enable traffic if isolation causes worse cascading"),
        PlaybookStep(step=3, action="Identify recovery path (replica, backup, redeploy)", owner="SRE", estimated_minutes=10),
        PlaybookStep(step=4, action="Execute recovery procedure", owner="SRE", estimated_minutes=20),
        PlaybookStep(step=5, action="Validate all downstream services recovered", owner="on-call", estimated_minutes=10, verification="All health checks green, error rate at baseline"),
        PlaybookStep(step=6, action="Update status page and notify stakeholders", owner="on-call", estimated_minutes=5),
        PlaybookStep(step=7, action="Conduct post-mortem within 48 hours", owner="on-call", estimated_minutes=60),
    ],
}

_SYSTEM_PROMPT = (
    "You are a senior SRE at a cloud-native company with deep expertise in AWS disaster recovery. "
    "You generate highly detailed, actionable runbooks grounded in the exact infrastructure context provided. "
    "Every step must reference specific AWS resource types, CLI commands with realistic placeholders, "
    "and clear verification criteria. Always respond with valid JSON only — "
    "no markdown, no code fences, no explanation outside the JSON."
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
            f"  - {n.get('name', '?')} [{n.get('type', 'unknown')}]"
            + (f" — region: {n['region']}" if n.get("region") else "")
            for n in nodes[:12]
        )

    doc_section = (
        f"\n## Relevant DR Documentation (from knowledge base)\n{doc_context[:3500]}"
        if doc_context.strip()
        else ""
    )

    schema = """{
  "summary": "One-sentence executive summary of the failure scenario and recovery approach",
  "business_impact": "Concrete description of user-facing and revenue impact during the outage",
  "risk_assessment": "Overall risk level of this recovery (low/medium/high) with specific caveats",
  "prerequisites": [
    "Condition or access that must be verified before starting recovery",
    "e.g. AWS Console access confirmed, PagerDuty incident created, stakeholders notified"
  ],
  "communication_plan": [
    "T+0: Page on-call SRE and DBA via PagerDuty",
    "T+5min: Post incident status to #incidents Slack channel",
    "T+15min: Notify Product and Customer Success if user impact confirmed",
    "T+30min: Executive update if RTO target will be missed"
  ],
  "steps": [
    {
      "step": 1,
      "action": "Specific, concrete action with resource names and region where applicable",
      "owner": "on-call|SRE|DBA|platform-team",
      "estimated_minutes": 5,
      "risk_level": "low|medium|high",
      "commands": [
        "aws cli or kubectl command with realistic <placeholder> values",
        "second command if needed"
      ],
      "verification": "Exact check to confirm this step succeeded (command output, metric, UI state)",
      "rollback": "Exact steps to safely undo this action if it makes things worse",
      "notes": "Any caveats, warnings, or context specific to this resource type"
    }
  ]
}"""

    return f"""Generate a comprehensive disaster recovery runbook for the following infrastructure failure.

## Failed Node
- Name: {node.get('name')}
- AWS Resource Type: {node.get('type')}
- Region: {node.get('region', 'us-east-1')}
- Recovery Strategy: {node.get('recovery_strategy', 'generic')}
- RTO Target: {node.get('rto_minutes', 60)} minutes
- RPO Target: {node.get('rpo_minutes', 15)} minutes

## Topology Context
### Downstream Services (directly impacted by this failure — {len(downstream)} nodes)
{_fmt_nodes(downstream)}

### Upstream Dependencies (services this node depends on — {len(upstream)} nodes)
{_fmt_nodes(upstream)}
{doc_section}

Return ONLY the following JSON (no other text):
{schema}

Requirements:
- Generate 7-10 highly specific steps tailored to {node.get('type')} in {node.get('region', 'us-east-1')}
- Each step MUST include: verification AND rollback (null only if truly not applicable)
- Commands must use real AWS CLI syntax for {node.get('type')} with <placeholder> values
- business_impact must quantify affected services (reference the {len(downstream)} downstream nodes)
- prerequisites must list actual access requirements (AWS Console, VPN, credentials)
- communication_plan must include realistic Slack/PagerDuty timing milestones
- risk_level: "high" for steps that touch production data or DNS, "medium" for config changes, "low" for observation"""


async def _call_claude(prompt: str, settings) -> str:
    """Call Claude API and return the raw text response."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    if message.stop_reason == "max_tokens":
        log.warning("playbook_claude_truncated", stop_reason="max_tokens")
    return message.content[0].text


def _extract_json(raw: str) -> dict:
    """
    Extract and parse the JSON object from Claude's response.
    If the response is truncated (unterminated string/array), salvage all
    complete steps by truncating at the last fully-closed step object.
    """
    json_start = raw.find("{")
    if json_start < 0:
        raise ValueError("No JSON object found in response")

    # Happy path: well-formed JSON
    json_end = raw.rfind("}") + 1
    candidate = raw[json_start:json_end]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Salvage path: truncated response — keep only complete step objects.
    # Find the last occurrence of `},` or `}` that closes a step (heuristic:
    # the pattern `"estimated_minutes": N }` marks a closed step object).
    # We rebuild a valid JSON by closing the steps array and outer object.
    last_complete = candidate.rfind("},\n")
    if last_complete < 0:
        last_complete = candidate.rfind("},")
    if last_complete < 0:
        raise ValueError("Cannot salvage any complete steps from truncated response")

    salvaged = candidate[: last_complete + 1] + "\n    ]\n}"
    try:
        parsed = json.loads(salvaged)
        log.warning("playbook_json_salvaged", steps_recovered=len(parsed.get("steps", [])))
        return parsed
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON salvage failed: {exc}") from exc


def _parse_steps(raw_steps: list[dict]) -> list[PlaybookStep]:
    steps = []
    for s in raw_steps:
        steps.append(PlaybookStep(
            step=s.get("step", len(steps) + 1),
            action=s.get("action", ""),
            owner=s.get("owner", "on-call"),
            estimated_minutes=s.get("estimated_minutes"),
            risk_level=s.get("risk_level", "low"),
            commands=s.get("commands") or [],
            verification=s.get("verification") or None,
            rollback=s.get("rollback") or None,
            notes=s.get("notes") or None,
        ))
    return steps


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
    Falls back to enriched static steps if Claude is unavailable or not configured.
    """
    if not force_regenerate and node_id in _playbook_cache:
        log.info("playbook_cache_hit", node_id=node_id)
        return _playbook_cache[node_id]

    # ── 1. Node details from Neo4j ────────────────────────────────────
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

    # ── 2. Topology: downstream + upstream ────────────────────────────
    downstream = await neo4j.run(
        "MATCH (n {id: $id})-[]->(dep:InfraNode) "
        "RETURN dep.name AS name, dep.type AS type, dep.region AS region LIMIT 15",
        {"id": node_id},
    )
    upstream = await neo4j.run(
        "MATCH (src:InfraNode)-[]->(n {id: $id}) "
        "RETURN src.name AS name, src.type AS type, src.region AS region LIMIT 15",
        {"id": node_id},
    )

    # ── 3. Qdrant RAG docs ────────────────────────────────────────────
    doc_context = ""
    doc_refs: list[str] = []
    if include_docs:
        try:
            from parsers.docs import _embed
            query = (
                f"disaster recovery runbook {node.get('type', '')} "
                f"{node.get('recovery_strategy', '')} AWS region {node.get('region', '')}"
            )
            vector = await _embed(query)
            docs = await qdrant.search(vector=vector, limit=5)
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

    # ── 4. Claude API generation ──────────────────────────────────────
    steps: list[PlaybookStep] = []
    summary = ""
    business_impact: str | None = None
    risk_assessment: str | None = None
    prerequisites: list[str] = []
    communication_plan: list[str] = []
    generation_source = "claude"
    llm_model = settings.anthropic_model
    use_claude = bool(settings.anthropic_api_key)

    if use_claude:
        try:
            prompt = _build_claude_prompt(node, downstream, upstream, doc_context)
            raw = await _call_claude(prompt, settings)
            parsed = _extract_json(raw)
            summary = parsed.get("summary", "")
            business_impact = parsed.get("business_impact")
            risk_assessment = parsed.get("risk_assessment")
            prerequisites = parsed.get("prerequisites") or []
            communication_plan = parsed.get("communication_plan") or []
            steps = _parse_steps(parsed.get("steps", []))

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

    # ── 5. Static fallback ────────────────────────────────────────────
    if not use_claude or not steps:
        strategy = node.get("recovery_strategy", "generic") or "generic"
        steps = _STATIC_STEPS_BY_STRATEGY.get(strategy, _STATIC_STEPS_BY_STRATEGY["generic"])
        summary = (
            f"Static recovery runbook for {node.get('name', node_id)} "
            f"using {strategy} strategy."
        )
        generation_source = "static"
        llm_model = "none"

    total_minutes = sum(s.estimated_minutes or 0 for s in steps) or None

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
        business_impact=business_impact,
        risk_assessment=risk_assessment,
        prerequisites=prerequisites,
        communication_plan=communication_plan,
        steps=steps,
        estimated_total_minutes=total_minutes,
        doc_references=[r for r in doc_refs if r],
        llm_model=llm_model,
        generation_source=generation_source,
    )

    _playbook_cache[node_id] = playbook
    return playbook
