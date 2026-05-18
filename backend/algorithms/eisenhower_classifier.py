"""
Eisenhower DR Classifier — maps disaster simulation results to priority quadrants.

  Q1: Urgent + Important  → act immediately, auto-invoke recovery plan
  Q2: Not Urgent + Important → schedule and plan
  Q3: Urgent + Not Important → delegate, watch escalation timer
  Q4: Not Urgent + Not Important → defer or accept

Constants:
  URGENCY_RATIO_WARN    — warn at 70% RTO/RPO utilisation (before actual breach)
  ESCALATION_WINDOW_MIN — Q3 promotes to Q1 after this many minutes unresolved
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.enhanced_graph import EnhancedSimulationWithTimeline


class EisenhowerQuadrant(str, Enum):
    Q1 = "Q1"   # Urgent + Important → act immediately
    Q2 = "Q2"   # Not Urgent + Important → schedule
    Q3 = "Q3"   # Urgent + Not Important → delegate
    Q4 = "Q4"   # Not Urgent + Not Important → defer


URGENCY_RATIO_WARN: float = 0.70
ESCALATION_WINDOW_MIN: float = 15.0

QUADRANT_MCP_ROUTES: dict[str, list[str]] = {
    "Q1": ["simulate_disaster", "get_recovery_plan"],
    "Q2": ["simulate_disaster"],
    "Q3": ["simulate_disaster"],
    "Q4": [],
}


@dataclass
class EisenhowerInput:
    simulation: "EnhancedSimulationWithTimeline"
    rto_target_minutes: float
    rpo_target_minutes: float
    cascade_in_progress: bool = False
    replication_lag_min: float = 0.0
    affects_production: bool = True


def classify_dr_event(inp: EisenhowerInput) -> EisenhowerQuadrant:
    """
    Classify a DR event into the Eisenhower matrix.

    Urgency criteria (any one triggers):
      - worst_case_rto_minutes exceeds the RTO target
      - replication lag exceeds the RPO target
      - cascade failure is already propagating

    Importance criteria (any one triggers):
      - event affects a production system
      - at least one node in blast radius is within 2 hops (critical proximity)
      - RTO is already breached (breach implies both urgency AND importance)
    """
    rto_breach = inp.simulation.worst_case_rto_minutes > inp.rto_target_minutes
    rpo_breach = inp.replication_lag_min > inp.rpo_target_minutes
    critical_blast = any(n.distance <= 2 for n in inp.simulation.blast_radius)

    is_urgent    = rto_breach or rpo_breach or inp.cascade_in_progress
    is_important = inp.affects_production or critical_blast or rto_breach

    if is_urgent and is_important:
        return EisenhowerQuadrant.Q1
    if not is_urgent and is_important:
        return EisenhowerQuadrant.Q2
    if is_urgent and not is_important:
        return EisenhowerQuadrant.Q3
    return EisenhowerQuadrant.Q4


def apply_escalation(
    quadrant: EisenhowerQuadrant,
    elapsed_minutes: float,
) -> EisenhowerQuadrant:
    """
    Promote Q3 to Q1 once the event has been unresolved for ESCALATION_WINDOW_MIN minutes.
    All other quadrants pass through unchanged.
    """
    if quadrant == EisenhowerQuadrant.Q3 and elapsed_minutes >= ESCALATION_WINDOW_MIN:
        return EisenhowerQuadrant.Q1
    return quadrant
