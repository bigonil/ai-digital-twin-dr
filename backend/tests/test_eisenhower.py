"""
Unit tests for Eisenhower DR Classifier.

Scenarios covered:
  1. 100% RTO breach → Q1 (urgent + important)
  2. 70% RTO utilisation, no breach → Q2 (not urgent, but important via affects_production)
  3. cascade_in_progress=True on non-critical, non-production node → Q3
  4. Q3 escalation to Q1 after ESCALATION_WINDOW_MIN elapsed
"""
import pytest

from algorithms.eisenhower_classifier import (
    ESCALATION_WINDOW_MIN,
    URGENCY_RATIO_WARN,
    EisenhowerInput,
    EisenhowerQuadrant,
    apply_escalation,
    classify_dr_event,
)
from models.enhanced_graph import (
    EnhancedAffectedNode,
    EnhancedSimulationWithTimeline,
    MonitoringState,
    RecoveryStrategy,
    TimelineStep,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _node(distance: int, rto: float = 30.0, rpo: float = 5.0) -> EnhancedAffectedNode:
    return EnhancedAffectedNode(
        id=f"node-d{distance}",
        name=f"Node depth={distance}",
        type="database",
        distance=distance,
        step_time_ms=distance * 1000,
        estimated_rto_minutes=rto,
        estimated_rpo_minutes=rpo,
        effective_rto_minutes=rto,
        effective_rpo_minutes=rpo,
        recovery_strategy=RecoveryStrategy.GENERIC,
        monitoring_state=MonitoringState.UNKNOWN,
    )


def _sim(
    worst_rto: float,
    worst_rpo: float,
    nodes: list[EnhancedAffectedNode],
) -> EnhancedSimulationWithTimeline:
    return EnhancedSimulationWithTimeline(
        origin_node_id="origin-001",
        blast_radius=nodes,
        timeline_steps=[],
        max_distance=max((n.distance for n in nodes), default=0),
        total_duration_ms=5000,
        worst_case_rto_minutes=worst_rto,
        worst_case_rpo_minutes=worst_rpo,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_classify_q1_full_rto_breach():
    """Scenario 1: worst_case_rto_minutes > rto_target → urgent + important → Q1."""
    nodes = [_node(0, rto=120), _node(1, rto=120), _node(2, rto=60)]
    sim = _sim(worst_rto=120.0, worst_rpo=5.0, nodes=nodes)

    inp = EisenhowerInput(
        simulation=sim,
        rto_target_minutes=60.0,   # RTO breach: 120 > 60
        rpo_target_minutes=15.0,
        cascade_in_progress=False,
        replication_lag_min=0.0,
        affects_production=True,
    )

    assert classify_dr_event(inp) == EisenhowerQuadrant.Q1


def test_classify_q2_partial_rto_at_warn_threshold():
    """Scenario 2: RTO at 70% of target (URGENCY_RATIO_WARN) — warn, but no breach.
    Not urgent (no breach, no cascade, no lag) + important (affects_production) → Q2.
    """
    rto_target = 60.0
    worst_rto = rto_target * URGENCY_RATIO_WARN   # 42.0 — exactly at the warning threshold

    # All nodes at distance >= 3 so critical_blast = False
    nodes = [_node(0, rto=worst_rto), _node(3, rto=worst_rto)]
    sim = _sim(worst_rto=worst_rto, worst_rpo=5.0, nodes=nodes)

    inp = EisenhowerInput(
        simulation=sim,
        rto_target_minutes=rto_target,
        rpo_target_minutes=15.0,
        cascade_in_progress=False,
        replication_lag_min=0.0,
        affects_production=True,   # important, but not urgent
    )

    assert classify_dr_event(inp) == EisenhowerQuadrant.Q2


def test_classify_q3_cascade_non_critical_non_production():
    """Scenario 3: cascade_in_progress=True but neither production nor critical blast → Q3."""
    # Nodes at depth >= 3 only → critical_blast = False
    # RTO well within target → no rto_breach
    nodes = [_node(3, rto=10.0), _node(5, rto=10.0)]
    sim = _sim(worst_rto=10.0, worst_rpo=2.0, nodes=nodes)

    inp = EisenhowerInput(
        simulation=sim,
        rto_target_minutes=60.0,    # no breach: 10 < 60
        rpo_target_minutes=15.0,
        cascade_in_progress=True,   # urgent
        replication_lag_min=0.0,
        affects_production=False,   # not important
    )

    assert classify_dr_event(inp) == EisenhowerQuadrant.Q3


def test_apply_escalation_promotes_q3_to_q1_after_window():
    """Scenario 4a: Q3 event unresolved past ESCALATION_WINDOW_MIN → promoted to Q1."""
    elapsed = ESCALATION_WINDOW_MIN + 1.0   # one minute past the window

    result = apply_escalation(EisenhowerQuadrant.Q3, elapsed_minutes=elapsed)
    assert result == EisenhowerQuadrant.Q1


def test_apply_escalation_q3_stays_q3_before_window():
    """Scenario 4b: Q3 event within ESCALATION_WINDOW_MIN → stays Q3."""
    elapsed = ESCALATION_WINDOW_MIN - 1.0

    result = apply_escalation(EisenhowerQuadrant.Q3, elapsed_minutes=elapsed)
    assert result == EisenhowerQuadrant.Q3


def test_apply_escalation_does_not_change_other_quadrants():
    """Escalation timer must not promote Q1, Q2, or Q4."""
    elapsed = ESCALATION_WINDOW_MIN + 100.0

    assert apply_escalation(EisenhowerQuadrant.Q1, elapsed) == EisenhowerQuadrant.Q1
    assert apply_escalation(EisenhowerQuadrant.Q2, elapsed) == EisenhowerQuadrant.Q2
    assert apply_escalation(EisenhowerQuadrant.Q4, elapsed) == EisenhowerQuadrant.Q4


def test_classify_q4_no_urgency_no_importance():
    """Edge case: nothing critical → Q4."""
    nodes = [_node(4, rto=5.0)]
    sim = _sim(worst_rto=5.0, worst_rpo=1.0, nodes=nodes)

    inp = EisenhowerInput(
        simulation=sim,
        rto_target_minutes=60.0,
        rpo_target_minutes=15.0,
        cascade_in_progress=False,
        replication_lag_min=0.0,
        affects_production=False,
    )

    assert classify_dr_event(inp) == EisenhowerQuadrant.Q4
