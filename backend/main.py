"""
Digital Twin DR — FastAPI entry point.
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from api import dr, graph, metrics
from db.neo4j_client import Neo4jClient
from db.qdrant_client import QdrantClient
from db.victoriametrics_client import VictoriaMetricsClient
from settings import Settings

settings = Settings()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", msg="Connecting to databases…")
    app.state.neo4j = Neo4jClient(settings)
    await app.state.neo4j.connect()

    app.state.vm = VictoriaMetricsClient(settings)

    app.state.qdrant = QdrantClient(settings)
    await app.state.qdrant.connect()

    log.info("startup", msg="All databases ready.")
    yield

    await app.state.neo4j.close()
    await app.state.qdrant.close()
    log.info("shutdown", msg="Connections closed.")


app = FastAPI(
    title="Digital Twin DR",
    version="0.1.0",
    description="Living Digital Twin for Disaster Recovery",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(dr.router, prefix="/api/dr", tags=["dr"])


@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok", "service": "digital-twin-dr"}
