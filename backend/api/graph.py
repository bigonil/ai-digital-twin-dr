"""Graph topology API endpoints."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from models.graph import InfraEdge, InfraGraph, InfraNode
from parsers import docs as docs_parser
from parsers import infra as infra_parser


class IngestTerraformRequest(BaseModel):
    directory: str


class IngestDocsRequest(BaseModel):
    directory: str

router = APIRouter()


@router.get("/topology", response_model=InfraGraph)
async def get_topology(request: Request):
    data = await request.app.state.neo4j.get_topology()
    nodes = [InfraNode(**n) for n in data["nodes"] if n.get("id")]
    edges = [InfraEdge(**e) for e in data["edges"] if e.get("source") and e.get("target")]
    return InfraGraph(nodes=nodes, edges=edges)


@router.get("/nodes", response_model=list[InfraNode])
async def list_nodes(request: Request):
    rows = await request.app.state.neo4j.run(
        "MATCH (n:InfraNode) RETURN n.id AS id, n.name AS name, n.type AS type, "
        "n.status AS status, n.provider AS provider, n.region AS region, "
        "n.az AS az, n.is_redundant AS is_redundant, "
        "n.rto_minutes AS rto_minutes, n.rpo_minutes AS rpo_minutes, labels(n) AS labels"
    )
    return [InfraNode(**r) for r in rows if r.get("id")]


@router.get("/nodes/{node_id}", response_model=InfraNode)
async def get_node(node_id: str, request: Request):
    rows = await request.app.state.neo4j.run(
        "MATCH (n {id: $id}) RETURN n.id AS id, n.name AS name, n.type AS type, "
        "n.status AS status, n.provider AS provider, n.region AS region, "
        "n.az AS az, n.is_redundant AS is_redundant, "
        "n.rto_minutes AS rto_minutes, n.rpo_minutes AS rpo_minutes, labels(n) AS labels",
        {"id": node_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return InfraNode(**rows[0])


@router.post("/ingest/terraform")
async def ingest_terraform(body: IngestTerraformRequest, request: Request):
    try:
        result = await infra_parser.ingest(body.directory, request.app.state.neo4j)
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ingest/docs")
async def ingest_docs(body: IngestDocsRequest, request: Request):
    try:
        result = await docs_parser.ingest(body.directory, request.app.state.qdrant, request.app.state.neo4j)
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
