"""
Observability module: OpenTelemetry tracing + custom Prometheus metrics.

Custom metrics:
  athena_simulation_latency_seconds      — histogram per simulation
  athena_neo4j_query_duration_seconds    — histogram per Neo4j query
  athena_simulation_cache_hits_total     — counter (hit/miss)
  athena_affected_nodes_per_simulation   — histogram of blast radius size
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Optional

import structlog
from prometheus_client import Counter, Histogram

log = structlog.get_logger()

# ── Custom Prometheus metrics ─────────────────────────────────────────────────

simulation_latency = Histogram(
    "athena_simulation_latency_seconds",
    "End-to-end BFS disaster simulation latency",
    ["origin_node_type"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

neo4j_query_duration = Histogram(
    "athena_neo4j_query_duration_seconds",
    "Neo4j Cypher query execution time",
    ["query_type"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

simulation_cache_hits = Counter(
    "athena_simulation_cache_hits_total",
    "Simulation cache hit/miss counter",
    ["result"],  # "hit" or "miss"
)

affected_nodes_histogram = Histogram(
    "athena_affected_nodes_per_simulation",
    "Number of nodes in simulation blast radius",
    buckets=[1, 2, 5, 10, 20, 50, 100],
)


# ── OpenTelemetry setup ───────────────────────────────────────────────────────

def setup_tracing(service_name: str, otlp_endpoint: Optional[str]) -> None:
    """
    Initialize OTel tracing. No-op if otlp_endpoint is empty/None.
    Exports spans to Jaeger/Tempo via OTLP gRPC.
    """
    if not otlp_endpoint:
        log.info("otel_tracing_disabled", reason="OTEL_ENDPOINT not set")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        resource = Resource.create({"service.name": service_name, "service.version": "1.0"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        log.info("otel_tracing_enabled", endpoint=otlp_endpoint, service=service_name)
    except Exception as exc:
        log.warning("otel_setup_failed", error=str(exc))


def instrument_fastapi(app) -> None:
    """Auto-instrument FastAPI routes with OTel spans."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass


def instrument_httpx() -> None:
    """Auto-instrument httpx calls (Ollama, VictoriaMetrics, etc.) with OTel spans."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except Exception:
        pass


def get_tracer(name: str):
    """Return OTel tracer; returns _NoopTracer if OTel is not initialized."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except Exception:
        return _NoopTracer()


# ── Noop fallback ─────────────────────────────────────────────────────────────

class _NoopSpan:
    def set_attribute(self, k, v): pass
    def record_exception(self, exc): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        yield _NoopSpan()
