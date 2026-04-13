"""
Phase 1 — Terraform HCL parser.
Reads .tf files, builds InfraNode + InfraEdge objects, upserts into Neo4j.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import hcl2
import structlog

from models.graph import CloudProvider, InfraEdge, InfraNode, ResourceStatus

log = structlog.get_logger()

PROVIDER_MAP: dict[str, CloudProvider] = {
    "aws": CloudProvider.aws,
    "google": CloudProvider.gcp,
    "azurerm": CloudProvider.azure,
}

REDUNDANCY_TYPES = {
    "aws_rds_cluster", "aws_elasticache_replication_group",
    "aws_lb", "aws_autoscaling_group", "google_compute_instance_group_manager",
    "azurerm_availability_set",
}


def _node_id(resource_type: str, resource_name: str) -> str:
    raw = f"{resource_type}.{resource_name}"
    return hashlib.md5(raw.encode()).hexdigest()[:12] + f"_{resource_name}"


def _detect_provider(resource_type: str) -> CloudProvider:
    prefix = resource_type.split("_")[0]
    return PROVIDER_MAP.get(prefix, CloudProvider.unknown)


def _extract_region(config: dict[str, Any]) -> str | None:
    return config.get("region") or config.get("location") or None


def _extract_az(config: dict[str, Any]) -> str | None:
    return config.get("availability_zone") or config.get("zone") or None


def _find_references(value: Any, current_id: str) -> list[str]:
    """Recursively hunt for ${resource_type.resource_name.*} references."""
    refs: list[str] = []
    if isinstance(value, str):
        for match in re.finditer(r'\$\{([a-z][a-z0-9_]*)\.([a-z][a-z0-9_-]*)\b', value):
            rtype, rname = match.group(1), match.group(2)
            ref_id = _node_id(rtype, rname)
            if ref_id != current_id:
                refs.append(ref_id)
    elif isinstance(value, dict):
        for v in value.values():
            refs.extend(_find_references(v, current_id))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_find_references(item, current_id))
    return refs


def parse_directory(terraform_dir: str | Path) -> tuple[list[InfraNode], list[InfraEdge]]:
    """Parse all .tf files in a directory tree."""
    base = Path(terraform_dir)
    nodes: dict[str, InfraNode] = {}
    edges: list[InfraEdge] = []

    tf_files = list(base.rglob("*.tf"))
    log.info("terraform.parse_start", directory=str(base), file_count=len(tf_files))

    for tf_file in tf_files:
        try:
            with open(tf_file, "r", encoding="utf-8") as fh:
                parsed = hcl2.load(fh)
        except Exception as exc:
            log.warning("terraform.parse_error", file=str(tf_file), error=str(exc))
            continue

        for resource_block in parsed.get("resource", []):
            for resource_type, instances in resource_block.items():
                for resource_name, config in instances.items():
                    node_id = _node_id(resource_type, resource_name)
                    node = InfraNode(
                        id=node_id,
                        name=resource_name,
                        type=resource_type,
                        provider=_detect_provider(resource_type),
                        region=_extract_region(config),
                        az=_extract_az(config),
                        status=ResourceStatus.unknown,
                        is_redundant=resource_type in REDUNDANCY_TYPES,
                        properties={
                            "source_file": str(tf_file.relative_to(base)),
                            "terraform_resource": f"{resource_type}.{resource_name}",
                        },
                        labels=["InfraNode", resource_type],
                    )
                    nodes[node_id] = node

                    for ref_id in _find_references(config, node_id):
                        edges.append(InfraEdge(source=node_id, target=ref_id, type="DEPENDS_ON"))

    log.info("terraform.parse_done", nodes=len(nodes), edges=len(edges))
    return list(nodes.values()), edges


async def ingest(terraform_dir: str | Path, neo4j_client) -> dict[str, int]:
    nodes, edges = parse_directory(terraform_dir)

    for node in nodes:
        await neo4j_client.merge_node(node.model_dump(), label="InfraNode")

    valid_ids = {n.id for n in nodes}
    ingested_edges = 0
    for edge in edges:
        if edge.target in valid_ids:
            await neo4j_client.merge_edge(edge.source, edge.target, edge.type, edge.properties)
            ingested_edges += 1

    return {"nodes": len(nodes), "edges": ingested_edges}
