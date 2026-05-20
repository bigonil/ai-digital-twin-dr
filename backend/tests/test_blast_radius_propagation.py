"""
Integration tests for blast-radius DEPENDS_ON propagation.

Tests the full topology defined in bootstrap_neo4j.py. Requires a live
backend at http://localhost:8001 with Neo4j seeded.

TOPOLOGY (source DEPENDS_ON target → source breaks when target fails):
  api-001  → lb-001
  api-002  → lb-001
  api-001  → db-001-primary
  api-002  → db-001-primary
  api-001  → cache-001
  api-002  → cache-001
  api-001  → queue-001
  api-002  → queue-001
  cache-001 → db-001-primary
  queue-001 → db-001-primary

Non-DEPENDS_ON edges (must NOT appear in blast radius):
  db-002-replica  -[:INTERACTS_WITH]-> db-001-primary
  backup-001      -[:STORES_IN]->      db-001-primary
  api-001         -[:READS_FROM]->     storage-001
  api-002         -[:READS_FROM]->     storage-001
  queue-001       -[:WRITES_TO]->      storage-001
"""
import pytest
import httpx

import os
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")

# Expected blast radius for every node in the topology.
# Key = failed node id. Value = {affected_node_id: expected_min_distance}.
# Origin node is excluded from all values (it's always at dist 0 in the response
# but is not a "dependent" — tested separately).
EXPECTED = {
    # Core database — everything that depends on it (directly or transitively)
    "db-001-primary": {
        "cache-001": 1,   # cache-001 DEPENDS_ON db-001-primary
        "queue-001": 1,   # queue-001 DEPENDS_ON db-001-primary
        "api-001":   1,   # api-001  DEPENDS_ON db-001-primary (direct, beats dist-2 path via cache)
        "api-002":   1,   # api-002  DEPENDS_ON db-001-primary (direct)
    },
    # Cache — apps that depend on it
    "cache-001": {
        "api-001": 1,
        "api-002": 1,
    },
    # Queue — apps that depend on it
    "queue-001": {
        "api-001": 1,
        "api-002": 1,
    },
    # Load balancer — apps that depend on it
    "lb-001": {
        "api-001": 1,
        "api-002": 1,
    },
    # Leaves — nothing depends on these nodes
    "api-001":        {},
    "api-002":        {},
    "db-002-replica": {},  # only INTERACTS_WITH, not DEPENDS_ON
    "storage-001":    {},  # only receives READS_FROM / WRITES_TO
    "backup-001":     {},  # only STORES_IN
}


def simulate(node_id: str, depth: int = 5) -> dict:
    import time
    for attempt in range(6):
        resp = httpx.post(
            f"{BASE_URL}/api/dr/simulate",
            json={"node_id": node_id, "depth": depth},
            timeout=15,
        )
        if resp.status_code == 429:
            # First retry waits 65s to fully clear the 1-minute rate-limit window;
            # subsequent retries use shorter backoff.
            time.sleep(65 if attempt == 0 else 5 * attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()  # final raise if still 429


# ---------------------------------------------------------------------------
# 1. Per-node blast radius correctness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("failed_node,expected_dependents", EXPECTED.items())
def test_blast_radius_exact_set(failed_node, expected_dependents):
    """Every node failure must produce exactly the expected set of dependents."""
    data = simulate(failed_node)
    br = data["blast_radius"]

    # Extract dependents only (exclude the origin at dist 0)
    actual = {n["id"]: n["distance"] for n in br if n["id"] != failed_node}

    missing = set(expected_dependents) - set(actual)
    unexpected = set(actual) - set(expected_dependents)

    assert not missing, (
        f"{failed_node} failure: expected these nodes in blast_radius but got none: {missing}. "
        f"Full actual dependents: {set(actual)}"
    )
    assert not unexpected, (
        f"{failed_node} failure: unexpected nodes in blast_radius: {unexpected}. "
        f"Check that non-DEPENDS_ON edges are not leaking into the cascade."
    )


@pytest.mark.parametrize("failed_node,expected_dependents", EXPECTED.items())
def test_blast_radius_distances(failed_node, expected_dependents):
    """Each dependent must appear at the correct minimum BFS distance."""
    data = simulate(failed_node)
    actual = {n["id"]: n["distance"] for n in data["blast_radius"] if n["id"] != failed_node}

    for node_id, expected_dist in expected_dependents.items():
        assert actual.get(node_id) == expected_dist, (
            f"{failed_node} failure: {node_id} expected at dist {expected_dist}, "
            f"got dist {actual.get(node_id)}"
        )


# ---------------------------------------------------------------------------
# 2. Origin node is always present at distance 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("node_id", EXPECTED.keys())
def test_origin_present_at_distance_zero(node_id):
    data = simulate(node_id)
    origin_entries = [n for n in data["blast_radius"] if n["id"] == node_id]
    assert len(origin_entries) == 1, f"Origin {node_id} not found in blast_radius"
    assert origin_entries[0]["distance"] == 0, (
        f"Origin {node_id} should be at distance 0, got {origin_entries[0]['distance']}"
    )


# ---------------------------------------------------------------------------
# 3. Minimum-distance wins over longer transitive paths
# ---------------------------------------------------------------------------

def test_minimum_distance_wins_over_transitive_path():
    """
    api-001 DEPENDS_ON db-001-primary directly (dist 1) AND transitively
    via cache-001 (dist 2) and queue-001 (dist 2). BFS must return dist 1.
    """
    data = simulate("db-001-primary")
    actual = {n["id"]: n["distance"] for n in data["blast_radius"]}
    assert actual["api-001"] == 1, (
        f"api-001 should be dist 1 (direct DEPENDS_ON db-001-primary), got {actual['api-001']}"
    )
    assert actual["api-002"] == 1, (
        f"api-002 should be dist 1 (direct), got {actual['api-002']}"
    )


# ---------------------------------------------------------------------------
# 4. Non-DEPENDS_ON edges must not contribute to blast radius
# ---------------------------------------------------------------------------

def test_interacts_with_does_not_cascade():
    """
    db-002-replica -[:INTERACTS_WITH]-> db-001-primary.
    Failing db-001-primary must NOT include db-002-replica in blast radius.
    """
    data = simulate("db-001-primary")
    affected_ids = {n["id"] for n in data["blast_radius"]}
    assert "db-002-replica" not in affected_ids, (
        "INTERACTS_WITH edge caused db-002-replica to appear in blast radius — "
        "only DEPENDS_ON should drive cascades."
    )


def test_stores_in_does_not_cascade():
    """
    backup-001 -[:STORES_IN]-> db-001-primary.
    Failing db-001-primary must NOT pull backup-001 into blast radius.
    """
    data = simulate("db-001-primary")
    affected_ids = {n["id"] for n in data["blast_radius"]}
    assert "backup-001" not in affected_ids, (
        "STORES_IN edge caused backup-001 to appear in blast radius."
    )


def test_reads_from_does_not_cascade():
    """
    api-001 -[:READS_FROM]-> storage-001.
    Failing storage-001 must NOT include api-001 in blast radius (wrong edge type).
    """
    data = simulate("storage-001")
    affected_ids = {n["id"] for n in data["blast_radius"]}
    assert "api-001" not in affected_ids, (
        "READS_FROM edge caused api-001 to appear in blast radius for storage-001 failure."
    )


# ---------------------------------------------------------------------------
# 5. Depth clamping
# ---------------------------------------------------------------------------

def test_depth_1_returns_only_direct_dependents():
    """At depth=1, only nodes with a single-hop DEPENDS_ON path to origin appear."""
    data = simulate("db-001-primary", depth=1)
    actual = {n["id"]: n["distance"] for n in data["blast_radius"] if n["id"] != "db-001-primary"}

    # All reachable in one hop from db-001-primary
    assert set(actual.keys()) == {"cache-001", "queue-001", "api-001", "api-002"}, (
        f"Depth-1 blast radius unexpected: {set(actual.keys())}"
    )
    for node_id, dist in actual.items():
        assert dist == 1, f"{node_id} should be dist 1 at depth=1, got {dist}"


def test_depth_clamp_maximum():
    """depth=20 (API max) is accepted; internally clamped to 10 — must not error."""
    data = simulate("db-001-primary", depth=20)
    assert "blast_radius" in data


def test_depth_above_api_max_returns_422():
    """depth=999 exceeds the Pydantic le=20 constraint — API must return 422."""
    resp = httpx.post(
        f"{BASE_URL}/api/dr/simulate",
        json={"node_id": "db-001-primary", "depth": 999},
        timeout=10,
    )
    assert resp.status_code == 422, f"Expected 422 for depth=999, got {resp.status_code}"


# ---------------------------------------------------------------------------
# 6. Leaf nodes have no dependents
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("leaf_node", ["api-001", "api-002"])
def test_leaf_nodes_have_empty_dependents(leaf_node):
    """api-001 and api-002 have nothing depending on them — blast radius = origin only."""
    data = simulate(leaf_node)
    dependents = [n for n in data["blast_radius"] if n["id"] != leaf_node]
    assert dependents == [], (
        f"{leaf_node} is a leaf but got unexpected dependents: {[n['id'] for n in dependents]}"
    )


# ---------------------------------------------------------------------------
# 7. Unknown node returns 404
# ---------------------------------------------------------------------------

def test_unknown_node_returns_404():
    resp = httpx.post(
        f"{BASE_URL}/api/dr/simulate",
        json={"node_id": "does-not-exist-xyz"},
        timeout=10,
    )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"


# ---------------------------------------------------------------------------
# 8. Response schema invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("node_id", EXPECTED.keys())
def test_response_schema(node_id):
    """Every simulation response must contain required fields."""
    data = simulate(node_id)
    required = {"blast_radius", "timeline_steps", "worst_case_rto_minutes",
                "worst_case_rpo_minutes", "eisenhower_quadrant", "origin_node_id"}
    missing = required - set(data.keys())
    assert not missing, f"Response missing fields: {missing}"
    assert data["origin_node_id"] == node_id


# ---------------------------------------------------------------------------
# 9. Critical node failures classified as Q1
# ---------------------------------------------------------------------------

def test_db_failure_is_q1_eisenhower():
    """Primary DB failure affects 4 nodes and must be Q1 (urgent + important)."""
    data = simulate("db-001-primary")
    assert data["eisenhower_quadrant"] == "Q1", (
        f"db-001-primary failure expected Q1, got {data['eisenhower_quadrant']}"
    )


def test_leaf_failure_is_not_q1():
    """api-001 failure (no dependents) should be Q3 or Q4, not Q1."""
    data = simulate("api-001")
    assert data["eisenhower_quadrant"] in {"Q2", "Q3", "Q4"}, (
        f"api-001 leaf failure expected Q2/Q3/Q4, got {data['eisenhower_quadrant']}"
    )
