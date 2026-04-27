"""Disaster Recovery API — simulate, plan, drift."""
from fastapi import APIRouter, HTTPException, Request

from models.graph import (
    AffectedNode,
    DisasterSimulationRequest,
    DisasterSimulationResult,
    SimulationWithTimeline,
    DriftResult,
)
from models.enhanced_graph import (
    EnhancedSimulationWithTimeline,
    EnhancedAffectedNode,
    TimelineStep,
)
from algorithms.cascading_failure import bfs_with_latency
from algorithms.rto_rpo_calculator import (
    calculate_effective_rto,
    calculate_effective_rpo,
    apply_monitoring_state_impact,
)

router = APIRouter()


def _calculate_step_times(affected_nodes: list[AffectedNode], total_duration_ms: int = 5000) -> tuple[list[AffectedNode], int, list[dict]]:
    """
    Calculate step_time_ms for each node based on BFS distance.

    Args:
        affected_nodes: List of affected nodes with distance field set
        total_duration_ms: Total animation duration in milliseconds

    Returns:
        (updated_affected_nodes, max_distance, timeline_steps_list)
    """
    if not affected_nodes:
        return affected_nodes, 0, []

    # Find max distance
    max_distance = max(node.distance for node in affected_nodes)

    # Calculate step_time_ms for each node
    updated_nodes = []
    timeline_steps = []

    for node in affected_nodes:
        # Distance 0 → 0ms (instant), distance N → proportional time
        step_time_ms = int(node.distance * (total_duration_ms / max_distance)) if max_distance > 0 else 0
        node.step_time_ms = step_time_ms
        updated_nodes.append(node)

        # Record timeline step for MCP agents
        timeline_steps.append({
            "node_id": node.id,
            "node_name": node.name,
            "distance": node.distance,
            "step_time_ms": step_time_ms,
            "rto_minutes": node.estimated_rto_minutes,
            "rpo_minutes": node.estimated_rpo_minutes,
        })

    # Sort timeline_steps by step_time_ms for easy playback
    timeline_steps.sort(key=lambda x: x["step_time_ms"])

    return updated_nodes, max_distance, timeline_steps


@router.post("/simulate", response_model=SimulationWithTimeline)
async def simulate_disaster(body: DisasterSimulationRequest, request: Request):
    """
    Simulate cascading failure with enhanced timing and RTO/RPO.
    Supports both legacy response (SimulationWithTimeline) and enhanced response (EnhancedSimulationWithTimeline)
    based on request context and algorithm availability.
    """
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

    # Calculate step times for timeline animation
    affected, max_distance, timeline_steps = _calculate_step_times(affected, total_duration_ms=5000)

    rtos = [a.estimated_rto_minutes for a in affected if a.estimated_rto_minutes]
    rpos = [a.estimated_rpo_minutes for a in affected if a.estimated_rpo_minutes]

    # Mark origin node and all affected nodes as simulated_failure in Neo4j
    await request.app.state.neo4j.run(
        "MATCH (n {id: $id}) SET n.status = 'simulated_failure'",
        {"id": body.node_id},
    )

    for node in affected:
        await request.app.state.neo4j.run(
            "MATCH (n {id: $id}) SET n.status = 'simulated_failure'",
            {"id": node.id},
        )

    return SimulationWithTimeline(
        origin_node_id=body.node_id,
        blast_radius=affected,
        total_affected=len(affected),
        worst_case_rto_minutes=max(rtos) if rtos else None,
        worst_case_rpo_minutes=max(rpos) if rpos else None,
        recovery_steps=_basic_recovery_steps(body.node_id, affected),
        max_distance=max_distance,
        total_duration_ms=5000,
        timeline_steps=timeline_steps,
    )


@router.post("/reset/{node_id}")
async def reset_node(node_id: str, request: Request):
    await request.app.state.neo4j.run(
        "MATCH (n {id: $id}) SET n.status = 'healthy'", {"id": node_id}
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
