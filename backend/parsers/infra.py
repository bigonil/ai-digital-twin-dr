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
from .strategy_inference import (
    infer_recovery_strategy,
    infer_edge_type,
    infer_recovery_rules,
    get_default_latency,
)

log = structlog.get_logger()

PROVIDER_MAP: dict[str, CloudProvider] = {
    "aws": CloudProvider.aws,
    "google": CloudProvider.gcp,
    "azurerm": CloudProvider.azure,
}

REDUNDANCY_TYPES = {
    "aws_rds_cluster", "aws_rds_cluster_instance", "aws_elasticache_replication_group",
    "aws_lb", "aws_autoscaling_group", "google_compute_instance_group_manager",
    "azurerm_availability_set",
}

# RTO/RPO defaults by resource type (in minutes)
RTO_RPO_MAP = {
    # Databases: low RTO/RPO with replication
    "aws_rds_cluster": (5, 1),
    "aws_rds_cluster_instance": (5, 1),
    "aws_db_instance": (10, 2),
    "azurerm_mssql_server": (10, 2),
    # Caching: very low RTO/RPO
    "aws_elasticache_cluster": (3, 1),
    "aws_elasticache_replication_group": (3, 1),
    # Load balancing & auto-scaling: fast recovery
    "aws_lb": (2, 0),
    "aws_autoscaling_group": (5, 1),
    # Compute: moderate RTO/RPO
    "aws_instance": (30, 10),
    "aws_lambda_function": (5, 1),
    "aws_ecs_service": (10, 2),
    # Storage: longer RTO, depends on backup
    "aws_s3_bucket": (60, 30),
    "aws_ebs_volume": (15, 5),
    # Networking: very fast
    "aws_vpc": (1, 0),
    "aws_subnet": (1, 0),
    "aws_security_group": (1, 0),
    # Default for unknown types
}


def _get_rto_rpo(resource_type: str) -> tuple[int, int]:
    """Return (RTO, RPO) in minutes for a resource type."""
    return RTO_RPO_MAP.get(resource_type, (60, 30))  # default: 60min RTO, 30min RPO


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


def _extract_resources(directory: str | Path) -> list[dict[str, Any]]:
    """
    Phase 1: Extract resources from Terraform files using hcl2 parsing.
    Returns raw resource dictionaries with metadata.
    """
    base = Path(directory)
    resources: list[dict[str, Any]] = []

    tf_files = list(base.rglob("*.tf"))
    log.info("terraform.phase1_extract_start", directory=str(base), file_count=len(tf_files))

    for tf_file in tf_files:
        try:
            with open(tf_file, "r", encoding="utf-8") as fh:
                parsed = hcl2.load(fh)
        except Exception as exc:
            log.warning("terraform.phase1_extract_error", file=str(tf_file), error=str(exc))
            continue

        for resource_block in parsed.get("resource", []):
            for resource_type, instances in resource_block.items():
                for resource_name, config in instances.items():
                    resource_id = _node_id(resource_type, resource_name)
                    resources.append({
                        "id": resource_id,
                        "type": resource_type,
                        "name": resource_name,
                        "config": config,
                        "source_file": str(tf_file.relative_to(base)),
                        "references": _find_references(config, resource_id),
                    })

    log.info("terraform.phase1_extract_done", resource_count=len(resources))
    return resources


def _infer_strategies(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Phase 2: Infer recovery strategy from resource type.
    """
    for resource in resources:
        resource_type = resource.get("type", "")
        resource["recovery_strategy"] = infer_recovery_strategy(resource_type)
    return resources


def _infer_edges(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Phase 3: Infer edge types from resource relationships.
    """
    # Build a map of resource IDs to resource objects for quick lookup
    resource_map = {r["id"]: r for r in resources}

    edges = []
    for resource in resources:
        source_type = resource.get("type", "")
        references = resource.get("references", [])

        for ref_id in references:
            target_resource = resource_map.get(ref_id)
            if not target_resource:
                continue

            target_type = target_resource.get("type", "")
            # If resource references ref_id, then ref_id impacts resource (ref_id → resource)
            edge_type = infer_edge_type(target_type, source_type)

            edges.append({
                "source": ref_id,
                "target": resource["id"],
                "type": edge_type,
            })

    return edges


def _set_default_latencies(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Phase 4: Set default latency per edge type.
    """
    for edge in edges:
        edge_type = edge.get("type", "DEPENDS_ON")
        edge["latency_ms"] = get_default_latency(edge_type)
        edge["latency_type"] = "static"
        edge["shares_resource"] = False
        edge["contention_factor"] = 1.0
    return edges


def _infer_all_recovery_rules(resources: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Phase 5: Infer recovery rules based on strategy and dependencies.
    """
    for resource in resources:
        strategy = resource.get("recovery_strategy", "generic")
        resource_id = resource["id"]

        # Check if resource has replicas or backups
        has_replica = any(
            e["source"] == resource_id and e["type"] == "REPLICATES_TO"
            for e in edges
        )
        has_backup = any(
            e["source"] == resource_id and e["type"] == "BACKED_UP_BY"
            for e in edges
        )

        rules = infer_recovery_rules(strategy, has_replica, has_backup)
        if rules:
            resource["recovery_rules"] = rules

    return resources


def _build_infra_nodes(resources: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[InfraNode], list[InfraEdge]]:
    """
    Phase 6: Create Neo4j objects from processed resources.
    """
    nodes: list[InfraNode] = []
    edge_list: list[InfraEdge] = []

    for resource in resources:
        resource_type = resource["type"]
        resource_name = resource["name"]
        config = resource["config"]
        tf_file = resource["source_file"]

        node_id = _node_id(resource_type, resource_name)
        rto, rpo = _get_rto_rpo(resource_type)

        node = InfraNode(
            id=node_id,
            name=resource_name,
            type=resource_type,
            provider=_detect_provider(resource_type),
            region=_extract_region(config),
            az=_extract_az(config),
            status=ResourceStatus.healthy,
            is_redundant=resource_type in REDUNDANCY_TYPES,
            rto_minutes=rto,
            rpo_minutes=rpo,
            properties={
                "source_file": tf_file,
                "terraform_resource": f"{resource_type}.{resource_name}",
            },
            labels=["InfraNode", resource_type],
        )
        nodes.append(node)

        # Extract references from config for edges
        # If node_id references ref_id, then ref_id impacts node_id (ref_id → node_id)
        for ref_id in _find_references(config, node_id):
            edge_list.append(InfraEdge(source=ref_id, target=node_id, type="DEPENDS_ON"))

    # Add edges from Phase 3 if any
    for edge in edges:
        edge_list.append(InfraEdge(
            source=edge.get("source"),
            target=edge.get("target"),
            type=edge.get("type", "DEPENDS_ON"),
        ))

    return nodes, edge_list


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
    """
    Six-phase Terraform parsing pipeline.

    Phase 1: Extract resources from Terraform files
    Phase 2: Infer recovery strategies (stub in Phase 1)
    Phase 3: Infer edge types (stub in Phase 1)
    Phase 4: Set default latencies (stub in Phase 1)
    Phase 5: Infer recovery rules (stub in Phase 1)
    Phase 6: Create Neo4j objects
    """
    log.info("terraform.parse_start", directory=str(terraform_dir))

    # Phase 1: Extract resources
    resources = _extract_resources(terraform_dir)

    # Phase 2: Infer strategies (implemented in Task 7)
    resources = _infer_strategies(resources)

    # Phase 3: Infer edges (implemented in Task 7)
    edges = _infer_edges(resources)

    # Phase 4: Set latencies (implemented in Task 7)
    edges = _set_default_latencies(edges)

    # Phase 5: Infer recovery rules (implemented in Task 7)
    resources = _infer_all_recovery_rules(resources, edges)

    # Phase 6: Create Neo4j objects
    nodes, edge_list = _build_infra_nodes(resources, edges)

    log.info("terraform.parse_done", nodes=len(nodes), edges=len(edge_list))
    return nodes, edge_list


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
