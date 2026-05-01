"""BFS algorithm for cascading failure propagation with latency accumulation"""

from typing import Dict, Callable, Any, List


def bfs_with_latency(
    origin_node_id: str,
    depth: int,
    get_outgoing_edges_fn: Callable[[str], List[Dict[str, Any]]],
    get_node_details_fn: Callable[[str], Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    BFS traversal with latency accumulation per hop.

    Args:
        origin_node_id: Starting node ID
        depth: Maximum hops to traverse
        get_outgoing_edges_fn: Function(node_id) → List[{target, latency_ms, shares_resource, contention_factor}]
        get_node_details_fn: Function(node_id) → {id, name, type, ...}

    Returns:
        Dict of affected nodes with step_time_ms: {node_id: {id, name, step_time_ms, ...}}
    """
    queue = [(origin_node_id, 0, 0, None)]  # (node_id, distance, base_latency, parent_id)
    affected_nodes = {}
    visited = set()

    while queue:
        current_node_id, distance, base_latency, parent_id = queue.pop(0)

        # Check depth limit and visited
        if distance > depth or current_node_id in visited:
            continue

        visited.add(current_node_id)

        # Calculate accumulated latency with contention if needed
        if parent_id and base_latency > 0:
            # Check if siblings with shared resources are already affected
            parent_edges = get_outgoing_edges_fn(parent_id)
            current_edge = next(
                (e for e in parent_edges if e["target"] == current_node_id),
                None
            )

            if current_edge and current_edge.get("shares_resource", False):
                # Check if any sibling is already affected (regardless of its shares_resource status)
                siblings_affected = any(
                    e["target"] in affected_nodes
                    for e in parent_edges
                    if e["target"] != current_node_id
                )
                if siblings_affected:
                    base_latency *= current_edge.get("contention_factor", 1.0)

        # Get parent's accumulated latency
        parent_latency = affected_nodes[parent_id]["step_time_ms"] if parent_id and parent_id in affected_nodes else 0
        acc_latency = parent_latency + base_latency

        # Record affected node
        node_details = get_node_details_fn(current_node_id)
        if node_details:
            affected_nodes[current_node_id] = {
                **node_details,
                "step_time_ms": acc_latency,
                "distance": distance,
            }

        # Process outgoing edges
        outgoing_edges = get_outgoing_edges_fn(current_node_id)

        for edge in outgoing_edges:
            target_node_id = edge["target"]
            edge_latency = edge.get("latency_ms", 100)
            queue.append((target_node_id, distance + 1, edge_latency, current_node_id))

    return affected_nodes


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
