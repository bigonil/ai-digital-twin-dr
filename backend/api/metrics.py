"""Metrics API — live health from VictoriaMetrics + Neo4j sync."""
from fastapi import APIRouter, Request

from models.graph import HealthStatus, ResourceStatus

router = APIRouter()


@router.get("/health/{node_id}", response_model=HealthStatus)
async def node_health(node_id: str, request: Request):
    raw = await request.app.state.vm.get_node_health(node_id)

    cpu = raw.get("cpu_percent")
    mem = raw.get("memory_percent")
    lag = raw.get("replication_lag_seconds")

    if cpu is not None and cpu > 90:
        status = ResourceStatus.degraded
    elif lag is not None and lag > 30:
        status = ResourceStatus.degraded
    else:
        status = ResourceStatus.healthy

    await request.app.state.neo4j.run(
        "MATCH (n {id: $id}) SET n.status = $status",
        {"id": node_id, "status": status.value},
    )

    return HealthStatus(
        node_id=node_id,
        status=status,
        cpu_percent=cpu,
        memory_percent=mem,
        replication_lag_seconds=lag,
    )


@router.get("/replication-lag")
async def replication_lag(request: Request):
    results = await request.app.state.vm.query("replication_lag_seconds")
    return {"data": results}
