"""BFS algorithm for cascading failure propagation with latency accumulation"""

from typing import Dict, Callable, Any, List

from algorithms.region_latency import get_geo_overhead_ms


async def bfs_with_latency(
    origin_node_id: str,
    depth: int,
    get_outgoing_edges_fn: Callable[[str], List[Dict[str, Any]]],
    get_node_details_fn: Callable[[str], Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    BFS traversal with latency accumulation per hop, including cross-region overhead.

    Args:
        origin_node_id: Starting node ID
        depth: Maximum hops to traverse
        get_outgoing_edges_fn: Async function(node_id) → List[{target, latency_ms, shares_resource, contention_factor}]
        get_node_details_fn: Async function(node_id) → {id, name, type, region, az, ...}

    Returns:
        Dict of affected nodes with step_time_ms: {node_id: {id, name, step_time_ms, cross_region, ...}}
    """
    queue = [(origin_node_id, 0, 0, None)]  # (node_id, distance, base_latency, parent_id)
    affected_nodes = {}
    visited = set()

    while queue:
        current_node_id, distance, base_latency, parent_id = queue.pop(0)

        if distance > depth or current_node_id in visited:
            continue

        visited.add(current_node_id)

        # Apply contention factor if siblings share resources
        if parent_id and base_latency > 0:
            parent_edges = await get_outgoing_edges_fn(parent_id)
            current_edge = next(
                (e for e in parent_edges if e["target"] == current_node_id),
                None
            )
            if current_edge and current_edge.get("shares_resource", False):
                siblings_affected = any(
                    e["target"] in affected_nodes
                    for e in parent_edges
                    if e["target"] != current_node_id
                )
                if siblings_affected:
                    base_latency *= current_edge.get("contention_factor", 1.0)

        parent_latency = affected_nodes[parent_id]["step_time_ms"] if parent_id and parent_id in affected_nodes else 0
        acc_latency = parent_latency + base_latency

        node_details = await get_node_details_fn(current_node_id)
        if node_details:
            affected_nodes[current_node_id] = {
                **node_details,
                "step_time_ms": acc_latency,
                "distance": distance,
                "cross_region": False,
            }

        # Process outgoing edges — add geographic overhead
        outgoing_edges = await get_outgoing_edges_fn(current_node_id)
        current_node_data = affected_nodes.get(current_node_id, {})

        for edge in outgoing_edges:
            target_node_id = edge["target"]
            edge_latency = edge.get("latency_ms", 100)

            # Add cross-region or cross-AZ overhead
            target_details = await get_node_details_fn(target_node_id)
            if target_details:
                geo_overhead = get_geo_overhead_ms(
                    current_node_data.get("region"),
                    current_node_data.get("az"),
                    target_details.get("region"),
                    target_details.get("az"),
                )
                edge_latency += geo_overhead
                if geo_overhead > 0 and target_node_id not in affected_nodes:
                    # Mark the target as a cross-region hop (set lazily after processing)
                    affected_nodes.setdefault(f"__flag_{target_node_id}", {"cross_region": True})

            queue.append((target_node_id, distance + 1, edge_latency, current_node_id))

    # Clean up temporary flag entries
    return {k: v for k, v in affected_nodes.items() if not k.startswith("__flag_")}


def calculate_step_times(affected_nodes: Dict[str, Dict[str, Any]],
                         total_duration_ms: int = 5000) -> List[Dict[str, Any]]:
    """
    Generate timeline steps from affected nodes for animation/MCP.

    Args:
        affected_nodes: Output from bfs_with_latency
        total_duration_ms: Total animation duration

    Returns:
        List of timeline steps sorted by step_time_ms
    """
    timeline_steps = []

    for node_id, node_data in affected_nodes.items():
        timeline_steps.append({
            "node_id": node_id,
            "node_name": node_data.get("name", node_id),
            "distance": node_data.get("distance", 0),
            "step_time_ms": node_data.get("step_time_ms", 0),
            "rto_minutes": node_data.get("rto_minutes", 0),
            "rpo_minutes": node_data.get("rpo_minutes", 0),
        })

    # Sort by step_time_ms for chronological animation
    timeline_steps.sort(key=lambda x: x["step_time_ms"])

    return timeline_steps
