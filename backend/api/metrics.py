"""Metrics API — live health from VictoriaMetrics + Neo4j sync."""
from datetime import datetime, timedelta
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
import structlog

from api.dependencies import limiter
from models.graph import HealthStatus, ResourceStatus

log = structlog.get_logger()
router = APIRouter()

_METRIC_PROMQL = {
    "cpu": 'node_cpu_usage_percent{{node_id="{}"}}',
    "memory": 'node_memory_usage_percent{{node_id="{}"}}',
    "replication_lag": 'replication_lag_seconds{{node_id="{}"}}',
}


class MetricPoint(BaseModel):
    timestamp: float  # Unix epoch seconds
    value: float


class MetricsRangeResponse(BaseModel):
    node_id: str
    metric: str
    points: list[MetricPoint]
    source: str  # "victoriametrics" or "mock"


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


@router.get("/range", response_model=MetricsRangeResponse)
async def get_metrics_range(
    request: Request,
    node_id: str = Query(..., description="Node ID to query"),
    metric: Literal["cpu", "memory", "replication_lag"] = Query("cpu"),
    hours: int = Query(24, ge=1, le=168, description="Lookback window in hours"),
):
    """
    Return historical metric timeseries from VictoriaMetrics.
    Falls back to empty list if VictoriaMetrics is unavailable.
    """
    try:
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        promql = _METRIC_PROMQL[metric].format(node_id)

        raw = await request.app.state.vm.query_range(
            promql=promql,
            start=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            step="5m",
        )

        points: list[MetricPoint] = []
        for series in raw:
            for ts, val in series.get("values", []):
                try:
                    points.append(MetricPoint(timestamp=float(ts), value=float(val)))
                except (TypeError, ValueError):
                    pass

        log.info("metrics_range_success", node_id=node_id, metric=metric, points=len(points))
        return MetricsRangeResponse(
            node_id=node_id,
            metric=metric,
            points=sorted(points, key=lambda p: p.timestamp),
            source="victoriametrics",
        )

    except HTTPException:
        raise
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.warning("metrics_range_fallback", node_id=node_id, metric=metric, error=str(exc), request_id=request_id)
        return MetricsRangeResponse(node_id=node_id, metric=metric, points=[], source="unavailable")


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
