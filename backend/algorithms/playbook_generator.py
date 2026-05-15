"""LLM-powered recovery playbook generation using Ollama + Qdrant context."""
import json
from datetime import datetime
from uuid import uuid4

import httpx
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


async def _call_ollama_llm(prompt: str, base_url: str, model: str) -> str:
    """Call Ollama /api/generate for text generation."""
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


def _build_llm_prompt(node: dict, deps: list[dict], doc_context: str) -> str:
    dep_names = ", ".join(d['name'] for d in deps[:5]) or "none"
    return f"""You are an SRE writing a disaster recovery runbook. Respond ONLY with valid JSON, no explanation.

Node: {node.get('name')} | Type: {node.get('type')} | Strategy: {node.get('recovery_strategy', 'generic')} | RTO: {node.get('rto_minutes')}min | Region: {node.get('region')}
Affected downstream: {dep_names}

Return JSON:
{{"summary": "one sentence", "steps": [{{"step": 1, "action": "...", "owner": "SRE|DBA|on-call", "estimated_minutes": 5, "commands": []}}]}}

Generate 5-7 steps specific to this failure."""


async def generate_playbook(
    node_id: str,
    neo4j,
    qdrant,
    settings,
    include_docs: bool = True,
    force_regenerate: bool = False,
) -> RecoveryPlaybook:
    """
    Generate LLM-powered recovery playbook for a node.
    Returns cached playbook if available (unless force_regenerate=True).
    Falls back to static steps if LLM is unavailable.
    """
    cache_key = node_id

    if not force_regenerate and cache_key in _playbook_cache:
        log.info("playbook_cache_hit", node_id=node_id)
        return _playbook_cache[cache_key]

    # Fetch node details from Neo4j
    rows = await neo4j.run(
        "MATCH (n:InfraNode {id: $id}) RETURN n.id AS id, n.name AS name, n.type AS type, "
        "n.recovery_strategy AS recovery_strategy, n.rto_minutes AS rto_minutes, "
        "n.rpo_minutes AS rpo_minutes, n.region AS region",
        {"id": node_id},
    )
    if not rows:
        raise ValueError(f"Node '{node_id}' not found")
    node = rows[0]

    # Fetch direct downstream dependencies
    dep_rows = await neo4j.run(
        "MATCH (n {id: $id})-[]->(dep:InfraNode) RETURN dep.name AS name, dep.type AS type LIMIT 10",
        {"id": node_id},
    )

    # Fetch relevant docs from Qdrant
    doc_context = ""
    doc_refs: list[str] = []
    if include_docs:
        try:
            from parsers.docs import _embed
            query = f"disaster recovery runbook for {node.get('type', '')} {node.get('recovery_strategy', '')}"
            vector = await _embed(query)
            docs = await qdrant.search(vector=vector, limit=3)
            if docs:
                doc_context = "\n---\n".join(d["payload"].get("text", "") for d in docs)
                doc_refs = [d["payload"].get("source_file", "") for d in docs if d.get("payload")]
        except Exception as exc:
            log.warning("playbook_qdrant_search_failed", error=str(exc))

    # Try LLM generation
    steps: list[PlaybookStep] = []
    summary = ""
    llm_model = settings.ollama_llm_model
    generation_source = "llm"

    try:
        prompt = _build_llm_prompt(node, dep_rows, doc_context)
        raw_response = await _call_ollama_llm(prompt, settings.ollama_base_url, llm_model)

        # Extract JSON from response
        json_start = raw_response.find("{")
        json_end = raw_response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(raw_response[json_start:json_end])
            summary = parsed.get("summary", "")
            for s in parsed.get("steps", []):
                steps.append(PlaybookStep(
                    step=s.get("step", len(steps) + 1),
                    action=s.get("action", ""),
                    owner=s.get("owner", "on-call"),
                    estimated_minutes=s.get("estimated_minutes"),
                    commands=s.get("commands", []),
                ))
        log.info("playbook_llm_success", node_id=node_id, steps=len(steps))

    except Exception as exc:
        log.warning("playbook_llm_failed", node_id=node_id, error=str(exc) or type(exc).__name__)
        strategy = node.get("recovery_strategy", "generic") or "generic"
        steps = _STATIC_STEPS_BY_STRATEGY.get(strategy, _STATIC_STEPS_BY_STRATEGY["generic"])
        summary = (
            f"Static recovery runbook for {node.get('name', node_id)} "
            f"using {strategy} strategy. LLM unavailable."
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

    _playbook_cache[cache_key] = playbook
    return playbook
