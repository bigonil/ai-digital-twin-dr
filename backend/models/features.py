"""
Features Models: Compliance, What-If, Chaos, Postmortem

All Pydantic schemas for the 4 new feature areas in branch 01_01_02.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# ============================================================================
# COMPLIANCE & TESTING
# ============================================================================

class ComplianceStatus(str, Enum):
    """RTO/RPO compliance status"""
    pass_ = "pass"
    fail = "fail"
    warning = "warning"
    skipped = "skipped"  # node has no rto_minutes set


class NodeComplianceResult(BaseModel):
    """Single node's compliance result"""
    node_id: str
    node_name: str
    node_type: str
    rto_minutes: Optional[int] = None
    rpo_minutes: Optional[int] = None
    rto_threshold: int
    rpo_threshold: int
    rto_status: ComplianceStatus
    rpo_status: ComplianceStatus
    blast_radius_size: int
    worst_case_rto: Optional[int] = None
    worst_case_rpo: Optional[int] = None


class ComplianceReport(BaseModel):
    """Compliance audit report"""
    generated_at: str  # ISO timestamp
    rto_threshold_minutes: int
    rpo_threshold_minutes: int
    total_nodes: int
    pass_count: int
    fail_count: int
    warning_count: int
    skipped_count: int
    results: list[NodeComplianceResult]


# ============================================================================
# ARCHITECTURE PLANNING (WHAT-IF SCENARIOS)
# ============================================================================

class VirtualNode(BaseModel):
    """A proposed node to add to the topology for what-if analysis"""
    id: str = Field(description="Must start with 'virtual-'")
    name: str
    type: str
    rto_minutes: Optional[int] = None
    rpo_minutes: Optional[int] = None
    is_redundant: bool = False

    @field_validator("id")
    @classmethod
    def id_must_be_virtual(cls, v):
        if not v.startswith("virtual-"):
            raise ValueError("VirtualNode id must start with 'virtual-'")
        return v


class VirtualEdge(BaseModel):
    """A proposed edge between nodes for what-if analysis"""
    source: str
    target: str
    type: str = "DEPENDS_ON"
    # Note: type is validated at endpoint level against _ALLOWED_REL_TYPES


class WhatIfRequest(BaseModel):
    """Request to simulate a what-if scenario"""
    origin_node_id: str
    depth: int = Field(default=5, ge=1, le=10)
    virtual_nodes: list[VirtualNode] = Field(default_factory=list)
    virtual_edges: list[VirtualEdge] = Field(default_factory=list)


class ScenarioComparison(BaseModel):
    """Comparison between baseline and proposed scenarios"""
    origin_node_id: str
    baseline: dict  # SimulationWithTimeline serialized
    proposed: dict  # SimulationWithTimeline serialized
    blast_radius_delta: int  # positive = worse (more affected), negative = better
    rto_delta_minutes: Optional[int] = None
    rpo_delta_minutes: Optional[int] = None
    virtual_nodes_added: int
    virtual_edges_added: int


# ============================================================================
# CHAOS ENGINEERING
# ============================================================================

class ChaosScenario(str, Enum):
    """Chaos engineering scenarios"""
    terminate = "terminate"              # node completely gone
    network_loss = "network_loss"        # edges severed
    cpu_hog = "cpu_hog"                  # degraded but present
    disk_full = "disk_full"
    memory_pressure = "memory_pressure"


class ChaosExperimentRequest(BaseModel):
    """Request to run a chaos engineering experiment"""
    node_id: str
    scenario: ChaosScenario
    depth: int = Field(default=5, ge=1, le=10)
    notes: str = ""


class ChaosExperimentRecord(BaseModel):
    """Recorded chaos engineering experiment"""
    experiment_id: str
    node_id: str
    node_name: str
    scenario: ChaosScenario
    created_at: str  # ISO timestamp
    simulation: dict  # SimulationWithTimeline serialized
    actual_rto_minutes: Optional[int] = None
    actual_blast_radius: list[str] = Field(default_factory=list)
    resilience_score: Optional[float] = None  # 0.0–1.0
    notes: str = ""


class ChaosActualResultRequest(BaseModel):
    """Submit actual results from a chaos engineering experiment"""
    actual_rto_minutes: Optional[int] = None
    actual_blast_radius: list[str]
    notes: str = ""


# ============================================================================
# INCIDENT POSTMORTEM
# ============================================================================

class PostmortemIncidentInput(BaseModel):
    """User input for postmortem analysis"""
    title: str
    occurred_at: str  # ISO timestamp
    actual_origin_node_id: str
    actually_failed_node_ids: list[str]
    actual_rto_minutes: int
    actual_rpo_minutes: Optional[int] = None
    reference_simulation_node_id: Optional[str] = None
    reference_simulation_depth: int = 5


class PostmortemPredictionAccuracy(BaseModel):
    """Prediction accuracy metrics"""
    predicted_node_ids: list[str]
    actual_node_ids: list[str]
    true_positives: list[str]
    false_positives: list[str]
    false_negatives: list[str]
    precision: float
    recall: float
    rto_delta_minutes: int  # actual - predicted (positive = took longer)
    accuracy_score: float  # 0.0–1.0 composite


class PostmortemReport(BaseModel):
    """Postmortem analysis report"""
    report_id: str
    title: str
    occurred_at: str  # ISO timestamp
    origin_node_id: str
    prediction_accuracy: PostmortemPredictionAccuracy
    simulation_used: Optional[dict] = None  # SimulationWithTimeline if available
    recommendations: list[str]
    created_at: str  # ISO timestamp


# ============================================================================
# RECOVERY PLAYBOOK (LLM-GENERATED)
# ============================================================================

class PlaybookStep(BaseModel):
    """A single step in a recovery playbook"""
    step: int
    action: str
    owner: str = "on-call"  # e.g., "DBA", "SRE", "on-call"
    estimated_minutes: Optional[int] = None
    commands: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class RecoveryPlaybook(BaseModel):
    """LLM-generated recovery runbook for a node failure"""
    playbook_id: str
    node_id: str
    node_name: str
    node_type: str
    recovery_strategy: str
    rto_minutes: Optional[int] = None
    rpo_minutes: Optional[int] = None
    generated_at: str  # ISO timestamp
    summary: str
    steps: list[PlaybookStep]
    doc_references: list[str] = Field(default_factory=list)  # Qdrant source_files used
    llm_model: str
    generation_source: str = "llm"  # "llm" or "static"


class PlaybookRequest(BaseModel):
    """Request to generate a recovery playbook"""
    node_id: str
    include_docs: bool = True  # search Qdrant for relevant docs
    force_regenerate: bool = False  # bypass cache
