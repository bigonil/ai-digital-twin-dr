"""Chaos Engineering API — experiment management and resilience scoring."""
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from models.features import (
    ChaosExperimentRequest,
    ChaosExperimentRecord,
    ChaosActualResultRequest,
)

router = APIRouter()


@router.post("/experiments", response_model=ChaosExperimentRecord)
async def run_chaos_experiment(body: ChaosExperimentRequest, request: Request):
    """
    Run a chaos engineering experiment.
    """
    neo4j = request.app.state.neo4j

    # Run simulation
    affected_rows = await neo4j.simulate_disaster(body.node_id, body.depth)

    # Extract node details
    node_detail = await neo4j.run(
        "MATCH (n {id: $id}) RETURN n.id AS id, n.name AS name, n.type AS type",
        {"id": body.node_id},
    )

    if not node_detail:
        raise HTTPException(status_code=404, detail=f"Node {body.node_id!r} not found")

    node_name = node_detail[0].get("name", body.node_id)
    node_type = node_detail[0].get("type", "unknown")

    # Extract worst-case times
    rtos = [r.get("rto_minutes") for r in affected_rows if r.get("rto_minutes")]
    rpos = [r.get("rpo_minutes") for r in affected_rows if r.get("rpo_minutes")]
    worst_rto = max(rtos) if rtos else None
    worst_rpo = max(rpos) if rpos else None

    # Build simulation dict
    simulation_dict = {
        "origin_node_id": body.node_id,
        "total_affected": len(affected_rows),
        "worst_case_rto_minutes": worst_rto,
        "worst_case_rpo_minutes": worst_rpo,
        "affected_nodes": [
            {
                "id": r.get("id"),
                "name": r.get("name", r.get("id")),
                "type": r.get("type", "unknown"),
                "distance": r.get("distance"),
                "rto_minutes": r.get("rto_minutes"),
                "rpo_minutes": r.get("rpo_minutes"),
            }
            for r in affected_rows
        ],
    }

    # Create experiment record
    experiment_id = str(uuid4())
    experiment = ChaosExperimentRecord(
        experiment_id=experiment_id,
        node_id=body.node_id,
        node_name=node_name,
        scenario=body.scenario,
        created_at=datetime.utcnow().isoformat(),
        simulation=simulation_dict,
        actual_rto_minutes=None,
        actual_blast_radius=[],
        resilience_score=None,
        notes=body.notes,
    )

    # Store in app state
    request.app.state.chaos_experiments[experiment_id] = experiment

    return experiment


@router.get("/experiments")
async def list_chaos_experiments(request: Request):
    """
    List all chaos experiments, sorted by created_at descending.
    """
    exps = request.app.state.chaos_experiments.values()
    sorted_exps = sorted(exps, key=lambda e: e.created_at, reverse=True)
    return [e.model_dump() for e in sorted_exps]


@router.get("/experiments/{experiment_id}", response_model=ChaosExperimentRecord)
async def get_chaos_experiment(experiment_id: str, request: Request):
    """
    Get a specific chaos experiment or 404.
    """
    exp = request.app.state.chaos_experiments.get(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id!r} not found")
    return exp


@router.post("/experiments/{experiment_id}/actuals", response_model=ChaosExperimentRecord)
async def submit_chaos_actuals(experiment_id: str, body: ChaosActualResultRequest, request: Request):
    """
    Submit actual results and compute resilience score.

    Resilience score = (rto_match + node_match) / 2
      - rto_match: 1.0 if actual <= predicted, else predicted/actual
      - node_match: intersection / union of predicted vs actual nodes
    """
    exp = request.app.state.chaos_experiments.get(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id!r} not found")

    # Extract predicted nodes
    predicted_nodes = {n["id"] for n in exp.simulation.get("affected_nodes", [])}
    actual_nodes = set(body.actual_blast_radius)

    # Compute RTO match
    predicted_rto = exp.simulation.get("worst_case_rto_minutes")
    actual_rto = body.actual_rto_minutes
    rto_match = 1.0

    if predicted_rto is not None and actual_rto is not None:
        if actual_rto <= predicted_rto:
            rto_match = 1.0
        else:
            rto_match = predicted_rto / actual_rto if actual_rto > 0 else 0.0
    elif predicted_rto is None and actual_rto is not None:
        rto_match = 0.5

    # Compute node match (Jaccard similarity)
    intersection = len(predicted_nodes & actual_nodes)
    union = len(predicted_nodes | actual_nodes)
    node_match = intersection / union if union > 0 else 1.0

    # Compute resilience score
    resilience_score = (rto_match + node_match) / 2.0

    # Update experiment
    exp.actual_rto_minutes = body.actual_rto_minutes
    exp.actual_blast_radius = list(body.actual_blast_radius)
    exp.resilience_score = resilience_score
    exp.notes = body.notes if body.notes else exp.notes

    request.app.state.chaos_experiments[experiment_id] = exp

    return exp


@router.delete("/experiments/{experiment_id}")
async def delete_chaos_experiment(experiment_id: str, request: Request):
    """
    Delete a chaos experiment.
    """
    if experiment_id not in request.app.state.chaos_experiments:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id!r} not found")

    del request.app.state.chaos_experiments[experiment_id]
    return {"status": "deleted", "experiment_id": experiment_id}
