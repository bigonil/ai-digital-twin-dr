"""Metrics API — live health from VictoriaMetrics + Neo4j sync."""
from fastapi import APIRouter, HTTPException, Request, status
import structlog

from api.dependencies import limiter
from models.graph import HealthStatus, ResourceStatus

log = structlog.get_logger()
router = APIRouter()


@router.get("/health/{node_id}", response_model=HealthStatus)
@limiter.limit("60/minute")
async def node_health(node_id: str, request: Request):
    try:
        # Verify node exists
        check = await request.app.state.neo4j.run(
            "MATCH (n {id: $id}) RETURN n.id LIMIT 1", {"id": node_id}
        )
        if not check:
            log.warning("node_health_not_found", node_id=node_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node '{node_id}' not found"
            )

        raw = await request.app.state.vm.get_node_health(node_id)

        cpu = raw.get("cpu_percent")
        mem = raw.get("memory_percent")
        lag = raw.get("replication_lag_seconds")

        if cpu is not None and cpu > 90:
            health_status = ResourceStatus.degraded
        elif lag is not None and lag > 30:
            health_status = ResourceStatus.degraded
        else:
            health_status = ResourceStatus.healthy

        await request.app.state.neo4j.run(
            "MATCH (n {id: $id}) SET n.status = $status",
            {"id": node_id, "status": health_status.value},
        )

        log.info("node_health_checked", node_id=node_id, status=health_status.value)
        return HealthStatus(
            node_id=node_id,
            status=health_status,
            cpu_percent=cpu,
            memory_percent=mem,
            replication_lag_seconds=lag,
        )
    except HTTPException:
        raise
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("node_health_error", node_id=node_id, error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch node health"
        )


@router.get("/replication-lag")
async def replication_lag(request: Request):
    try:
        results = await request.app.state.vm.query("replication_lag_seconds")
        log.info("replication_lag_query_success")
        return {"data": results}
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("replication_lag_error", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query replication lag"
        )
