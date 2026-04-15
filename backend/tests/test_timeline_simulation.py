import pytest
from models.graph import AffectedNode
from api.dr import _calculate_step_times


def test_calculate_step_times_single_node():
    """Test step times with just the origin node."""
    nodes = [
        AffectedNode(
            id="node-0",
            name="Origin",
            type="database",
            distance=0,
        )
    ]

    updated, max_dist, steps = _calculate_step_times(nodes, total_duration_ms=5000)

    assert max_dist == 0
    assert len(steps) == 1
    assert steps[0]["step_time_ms"] == 0


def test_calculate_step_times_cascade():
    """Test step times with cascading failures."""
    nodes = [
        AffectedNode(id="n0", name="Origin", type="db", distance=0),
        AffectedNode(id="n1", name="App1", type="app", distance=1),
        AffectedNode(id="n2", name="App2", type="app", distance=1),
        AffectedNode(id="n3", name="Cache", type="cache", distance=2),
    ]

    updated, max_dist, steps = _calculate_step_times(nodes, total_duration_ms=5000)

    assert max_dist == 2
    assert len(steps) == 4

    # Check step times are proportional to distance
    step_map = {s["node_id"]: s["step_time_ms"] for s in steps}

    assert step_map["n0"] == 0  # distance 0
    assert step_map["n1"] == 2500  # distance 1 → 50% of total
    assert step_map["n2"] == 2500  # distance 1
    assert step_map["n3"] == 5000  # distance 2 → 100% of total


def test_calculate_step_times_sorted():
    """Test that timeline_steps are sorted by step_time_ms."""
    nodes = [
        AffectedNode(id="n3", name="X", type="x", distance=2),
        AffectedNode(id="n0", name="X", type="x", distance=0),
        AffectedNode(id="n1", name="X", type="x", distance=1),
    ]

    _, _, steps = _calculate_step_times(nodes, total_duration_ms=5000)

    # Steps should be sorted by step_time_ms
    for i in range(len(steps) - 1):
        assert steps[i]["step_time_ms"] <= steps[i + 1]["step_time_ms"]


def test_calculate_step_times_custom_duration():
    """Test with custom total duration."""
    nodes = [
        AffectedNode(id="n0", name="X", type="x", distance=0),
        AffectedNode(id="n1", name="X", type="x", distance=1),
    ]

    _, max_dist, steps = _calculate_step_times(nodes, total_duration_ms=10000)

    step_map = {s["node_id"]: s["step_time_ms"] for s in steps}
    assert step_map["n0"] == 0
    assert step_map["n1"] == 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
