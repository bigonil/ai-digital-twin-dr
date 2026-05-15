"""Graph topology API endpoints."""
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
import structlog

from api.dependencies import limiter
from models.graph import InfraEdge, InfraGraph, InfraNode
from parsers import docs as docs_parser
from parsers import infra as infra_parser

log = structlog.get_logger()


class IngestTerraformRequest(BaseModel):
    directory: str


class IngestDocsRequest(BaseModel):
    directory: str

router = APIRouter()


@router.get("/topology", response_model=InfraGraph)
async def get_topology(request: Request):
    try:
        data = await request.app.state.neo4j.get_topology()
        nodes = [InfraNode(**n) for n in data["nodes"] if n.get("id")]
        edges = [InfraEdge(**e) for e in data["edges"] if e.get("source") and e.get("target")]
        log.info("topology_fetched", node_count=len(nodes), edge_count=len(edges))
        return InfraGraph(nodes=nodes, edges=edges)
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("topology_error", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch topology"
        )


@router.get("/nodes", response_model=list[InfraNode])
async def list_nodes(request: Request):
    try:
        rows = await request.app.state.neo4j.run(
            "MATCH (n:InfraNode) RETURN n.id AS id, n.name AS name, n.type AS type, "
            "n.status AS status, n.provider AS provider, n.region AS region, "
            "n.az AS az, n.is_redundant AS is_redundant, "
            "n.rto_minutes AS rto_minutes, n.rpo_minutes AS rpo_minutes, labels(n) AS labels"
        )
        nodes = [InfraNode(**r) for r in rows if r.get("id")]
        log.info("nodes_listed", count=len(nodes))
        return nodes
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("list_nodes_error", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list nodes"
        )


@router.get("/nodes/{node_id}", response_model=InfraNode)
async def get_node(node_id: str, request: Request):
    try:
        rows = await request.app.state.neo4j.run(
            "MATCH (n {id: $id}) RETURN n.id AS id, n.name AS name, n.type AS type, "
            "n.status AS status, n.provider AS provider, n.region AS region, "
            "n.az AS az, n.is_redundant AS is_redundant, "
            "n.rto_minutes AS rto_minutes, n.rpo_minutes AS rpo_minutes, labels(n) AS labels",
            {"id": node_id},
        )
        if not rows:
            log.warning("node_not_found", node_id=node_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node '{node_id}' not found"
            )
        return InfraNode(**rows[0])
    except HTTPException:
        raise
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("get_node_error", node_id=node_id, error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch node"
        )


@router.post("/ingest/terraform")
@limiter.limit("30/minute")
async def ingest_terraform(body: IngestTerraformRequest, request: Request):
    try:
        result = await infra_parser.ingest(body.directory, request.app.state.neo4j)
        log.info("terraform_ingestion_success", directory=body.directory, **result)
        return {"status": "ok", **result}
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("terraform_ingestion_error", directory=body.directory, error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Terraform ingestion failed"
        ) from exc


@router.post("/ingest/docs")
@limiter.limit("30/minute")
async def ingest_docs(body: IngestDocsRequest, request: Request):
    try:
        result = await docs_parser.ingest(body.directory, request.app.state.qdrant, request.app.state.neo4j)
        log.info("docs_ingestion_success", directory=body.directory, **result)
        return {"status": "ok", **result}
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("docs_ingestion_error", directory=body.directory, error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Documentation ingestion failed"
        ) from exc
