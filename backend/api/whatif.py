"""Architecture Planning API — what-if scenario analysis."""
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from models.features import WhatIfRequest, ScenarioComparison
from models.graph import SimulationWithTimeline

router = APIRouter()


def _simulate_to_dict(sim: SimulationWithTimeline) -> dict:
    """Convert SimulationWithTimeline to dict for comparison storage."""
    return {
        "origin_node_id": sim.origin_node_id,
        "total_affected": sim.total_affected,
        "worst_case_rto_minutes": sim.worst_case_rto_minutes,
        "worst_case_rpo_minutes": sim.worst_case_rpo_minutes,
        "blast_radius": [node.model_dump() for node in sim.blast_radius],
    }


@router.post("/simulate", response_model=ScenarioComparison)
async def run_whatif_simulation(body: WhatIfRequest, request: Request):
    """
    Run what-if scenario analysis:
    1. Run baseline simulation
    2. Merge virtual nodes and edges
    3. Run proposed simulation
    4. Delete virtual nodes (cleanup)
    5. Return comparison
    """
    neo4j = request.app.state.neo4j
    origin = body.origin_node_id

    # Run baseline simulation
    baseline_rows = await neo4j.simulate_disaster(origin, body.depth)
    baseline_rtos = [r.get("rto_minutes") for r in baseline_rows if r.get("rto_minutes")]
    baseline_rpo = [r.get("rpo_minutes") for r in baseline_rows if r.get("rpo_minutes")]
    baseline_worst_rto = max(baseline_rtos) if baseline_rtos else None
    baseline_worst_rpo = max(baseline_rpo) if baseline_rpo else None
    baseline_blast_size = len(baseline_rows)

    baseline_sim = SimulationWithTimeline(
        origin_node_id=origin,
        blast_radius=[],
        total_affected=baseline_blast_size,
        worst_case_rto_minutes=baseline_worst_rto,
        worst_case_rpo_minutes=baseline_worst_rpo,
        recovery_steps=[],
        max_distance=0,
        total_duration_ms=0,
    )

    try:
        # Merge virtual nodes
        for vnode in body.virtual_nodes:
            node_data = {
                "id": vnode.id,
                "name": vnode.name,
                "type": vnode.type,
                "is_redundant": vnode.is_redundant,
            }
            if vnode.rto_minutes is not None:
                node_data["rto_minutes"] = vnode.rto_minutes
            if vnode.rpo_minutes is not None:
                node_data["rpo_minutes"] = vnode.rpo_minutes
            await neo4j.merge_node(node_data)

        # Merge virtual edges
        for vedge in body.virtual_edges:
            # Validate edge type
            if vedge.type not in {"DEPENDS_ON", "INTERACTS_WITH", "DOCUMENTED_BY", "STORES_IN", "READS_FROM", "WRITES_TO", "DEPLOYED_ON"}:
                raise ValueError(f"Invalid relationship type: {vedge.type}")
            await neo4j.merge_edge(vedge.source, vedge.target, vedge.type)

        # Run proposed simulation
        proposed_rows = await neo4j.simulate_disaster(origin, body.depth)
        proposed_rtos = [r.get("rto_minutes") for r in proposed_rows if r.get("rto_minutes")]
        proposed_rpos = [r.get("rpo_minutes") for r in proposed_rows if r.get("rpo_minutes")]
        proposed_worst_rto = max(proposed_rtos) if proposed_rtos else None
        proposed_worst_rpo = max(proposed_rpos) if proposed_rpos else None
        proposed_blast_size = len(proposed_rows)

        proposed_sim = SimulationWithTimeline(
            origin_node_id=origin,
            blast_radius=[],
            total_affected=proposed_blast_size,
            worst_case_rto_minutes=proposed_worst_rto,
            worst_case_rpo_minutes=proposed_worst_rpo,
            recovery_steps=[],
            max_distance=0,
            total_duration_ms=0,
        )

        # Calculate deltas
        blast_radius_delta = proposed_blast_size - baseline_blast_size
        rto_delta = None
        rpo_delta = None

        if baseline_worst_rto is not None and proposed_worst_rto is not None:
            rto_delta = proposed_worst_rto - baseline_worst_rto
        if baseline_worst_rpo is not None and proposed_worst_rpo is not None:
            rpo_delta = proposed_worst_rpo - baseline_worst_rpo

        comparison = ScenarioComparison(
            origin_node_id=origin,
            baseline=_simulate_to_dict(baseline_sim),
            proposed=_simulate_to_dict(proposed_sim),
            blast_radius_delta=blast_radius_delta,
            rto_delta_minutes=rto_delta,
            rpo_delta_minutes=rpo_delta,
            virtual_nodes_added=len(body.virtual_nodes),
            virtual_edges_added=len(body.virtual_edges),
        )

        return comparison

    finally:
        # Cleanup: delete all virtual nodes
        await neo4j.run("MATCH (n) WHERE n.id STARTS WITH 'virtual-' DETACH DELETE n")
