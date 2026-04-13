"""Disaster Recovery API — simulate, plan, drift."""
from fastapi import APIRouter, HTTPException, Request

from models.graph import (
    AffectedNode,
    DisasterSimulationRequest,
    DisasterSimulationResult,
    DriftResult,
)

router = APIRouter()


@router.post("/simulate", response_model=DisasterSimulationResult)
async def simulate_disaster(body: DisasterSimulationRequest, request: Request):
    rows = await request.app.state.neo4j.simulate_disaster(body.node_id, body.depth)

    if not rows and body.node_id:
        check = await request.app.state.neo4j.run(
            "MATCH (n {id: $id}) RETURN n.id", {"id": body.node_id}
        )
        if not check:
            raise HTTPException(status_code=404, detail=f"Node {body.node_id!r} not found")

    affected = [
        AffectedNode(
            id=r["id"],
            name=r.get("name", r["id"]),
            type=r.get("type", "unknown"),
            distance=r["distance"],
            estimated_rto_minutes=r.get("rto_minutes"),
            estimated_rpo_minutes=r.get("rpo_minutes"),
        )
        for r in rows
    ]

    rtos = [a.estimated_rto_minutes for a in affected if a.estimated_rto_minutes]
    rpos = [a.estimated_rpo_minutes for a in affected if a.estimated_rpo_minutes]

    await request.app.state.neo4j.run(
        "MATCH (n {id: $id}) SET n.status = 'simulated_failure'",
        {"id": body.node_id},
    )

    return DisasterSimulationResult(
        origin_node_id=body.node_id,
        blast_radius=affected,
        total_affected=len(affected),
        worst_case_rto_minutes=max(rtos) if rtos else None,
        worst_case_rpo_minutes=max(rpos) if rpos else None,
        recovery_steps=_basic_recovery_steps(body.node_id, affected),
    )


@router.post("/reset/{node_id}")
async def reset_node(node_id: str, request: Request):
    await request.app.state.neo4j.run(
        "MATCH (n {id: $id}) SET n.status = 'unknown'", {"id": node_id}
    )
    return {"reset": node_id}


@router.get("/drift", response_model=DriftResult)
async def check_drift(request: Request):
    """Compare Neo4j InfraNodes vs last-known Terraform state (stub)."""
    graph_nodes = await request.app.state.neo4j.run(
        "MATCH (n:InfraNode) RETURN n.id AS id"
    )
    graph_ids = {r["id"] for r in graph_nodes}
    return DriftResult(
        nodes_in_graph_only=sorted(graph_ids),
        nodes_in_terraform_only=[],
        drifted_properties=[],
    )


def _basic_recovery_steps(origin: str, affected: list[AffectedNode]) -> list[str]:
    steps = [
        f"1. Acknowledge incident — origin node: {origin}",
        "2. Notify on-call team via PagerDuty / OpsGenie",
        "3. Isolate failed node to prevent cascading writes",
    ]
    for i, node in enumerate(affected[:5], start=4):
        steps.append(f"{i}. Restore {node.name} ({node.type}) — est. RTO {node.estimated_rto_minutes} min")
    steps.append(f"{len(steps) + 1}. Run smoke-tests and validate replication lag < threshold")
    steps.append(f"{len(steps) + 1}. Mark incident resolved and update runbook")
    return steps
