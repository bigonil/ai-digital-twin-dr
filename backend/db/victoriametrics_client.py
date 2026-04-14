"""VictoriaMetrics async HTTP client (PromQL instant & range queries)."""
import re
import structlog
import httpx

log = structlog.get_logger()

# Valid node-id pattern: alphanumeric, underscores, hyphens, dots
_NODE_ID_RE = re.compile(r"^[\w\-\.]+$")


class VictoriaMetricsClient:
    def __init__(self, settings):
        self._base_url = settings.victoriametrics_url
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def query(self, promql: str) -> list[dict]:
        """Instant query — returns list of {metric, value} dicts."""
        resp = await self._client.get("/api/v1/query", params={"query": promql})
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("result", [])

    async def query_range(self, promql: str, start: str, end: str, step: str = "60s") -> list[dict]:
        resp = await self._client.get(
            "/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("result", [])

    async def get_node_health(self, node_id: str) -> dict:
        """Aggregate health signals for a single node."""
        if not _NODE_ID_RE.match(node_id):
            raise ValueError(f"Invalid node_id format: {node_id!r}")
        cpu = await self._safe_scalar(f'node_cpu_usage_percent{{node_id="{node_id}"}}')
        mem = await self._safe_scalar(f'node_memory_usage_percent{{node_id="{node_id}"}}')
        lag = await self._safe_scalar(f'replication_lag_seconds{{node_id="{node_id}"}}')
        return {"cpu_percent": cpu, "memory_percent": mem, "replication_lag_seconds": lag}

    async def _safe_scalar(self, promql: str) -> float | None:
        try:
            results = await self.query(promql)
            if results:
                return float(results[0]["value"][1])
        except Exception:
            pass
        return None

    async def close(self):
        await self._client.aclose()
