"""
Phase 2 — Static code analysis.
Scans Python / JavaScript source for cloud SDK calls and connection strings,
links Function nodes to InfraNode resources in Neo4j.
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import structlog

from models.graph import InfraEdge, InfraNode, CloudProvider, ResourceStatus

log = structlog.get_logger()

# SDK import → resource type heuristic
SDK_PATTERNS: dict[str, str] = {
    "boto3": "aws_sdk",
    "botocore": "aws_sdk",
    "google.cloud": "gcp_sdk",
    "azure": "azure_sdk",
}

# Patterns for connection string extraction
CONN_STRING_RE = re.compile(
    r'(?:endpoint|url|host|bucket|queue|table)\s*=\s*["\']([^"\']{8,})["\']',
    re.IGNORECASE,
)

# boto3 service → resource type mapping
BOTO3_SERVICE_MAP = {
    "s3": "aws_s3_bucket",
    "rds": "aws_db_instance",
    "dynamodb": "aws_dynamodb_table",
    "sqs": "aws_sqs_queue",
    "sns": "aws_sns_topic",
    "lambda": "aws_lambda_function",
    "ec2": "aws_instance",
    "elb": "aws_lb",
    "elbv2": "aws_lb",
    "elasticache": "aws_elasticache_cluster",
}


def _func_id(file_path: str, func_name: str) -> str:
    raw = f"{file_path}::{func_name}"
    return "fn_" + hashlib.md5(raw.encode()).hexdigest()[:10]


def _resource_id_from_name(resource_name: str) -> str:
    return "ref_" + hashlib.md5(resource_name.encode()).hexdigest()[:10]


def _scan_python_file(file_path: Path, base: Path) -> tuple[list[InfraNode], list[InfraEdge]]:
    nodes: list[InfraNode] = []
    edges: list[InfraEdge] = []
    rel_path = str(file_path.relative_to(base))

    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return nodes, edges

    # Collect boto3 client calls: boto3.client("s3"), boto3.resource("dynamodb")
    boto3_services: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "boto3"
                and node.func.attr in ("client", "resource")
            ):
                if node.args and isinstance(node.args[0], ast.Constant):
                    boto3_services.add(str(node.args[0].value).lower())

    # Walk function definitions
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_id = _func_id(rel_path, node.name)
            func_node = InfraNode(
                id=func_id,
                name=node.name,
                type="CodeFunction",
                provider=CloudProvider.unknown,
                status=ResourceStatus.unknown,
                labels=["Function"],
                properties={"source_file": rel_path, "language": "python"},
            )
            nodes.append(func_node)

            # Link to detected SDK resource types
            for svc in boto3_services:
                res_type = BOTO3_SERVICE_MAP.get(svc, f"aws_{svc}")
                res_ref_id = _resource_id_from_name(res_type)
                edges.append(InfraEdge(source=func_id, target=res_ref_id, type="INTERACTS_WITH",
                                       properties={"sdk": "boto3", "service": svc}))

    # Connection strings as lightweight reference nodes
    for match in CONN_STRING_RE.finditer(source):
        ref = match.group(1)
        ref_id = _resource_id_from_name(ref)
        ref_node = InfraNode(
            id=ref_id, name=ref[:64], type="ExternalEndpoint",
            provider=CloudProvider.unknown, status=ResourceStatus.unknown,
            labels=["ExternalEndpoint"],
            properties={"source_file": rel_path, "connection_string": ref},
        )
        nodes.append(ref_node)

    return nodes, edges


def scan_directory(src_dir: str | Path) -> tuple[list[InfraNode], list[InfraEdge]]:
    base = Path(src_dir)
    all_nodes: list[InfraNode] = []
    all_edges: list[InfraEdge] = []

    for py_file in base.rglob("*.py"):
        n, e = _scan_python_file(py_file, base)
        all_nodes.extend(n)
        all_edges.extend(e)

    log.info("code.scan_done", nodes=len(all_nodes), edges=len(all_edges))
    return all_nodes, all_edges


async def ingest(src_dir: str | Path, neo4j_client) -> dict[str, int]:
    nodes, edges = scan_directory(src_dir)
    for node in nodes:
        label = node.labels[0] if node.labels else "Function"
        await neo4j_client.merge_node(node.model_dump(), label=label)

    ingested = 0
    node_ids = {n.id for n in nodes}
    for edge in edges:
        if edge.source in node_ids:
            await neo4j_client.merge_edge(edge.source, edge.target, edge.type, edge.properties)
            ingested += 1

    return {"nodes": len(nodes), "edges": ingested}
