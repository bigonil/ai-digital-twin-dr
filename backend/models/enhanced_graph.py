from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class RecoveryStrategy(str, Enum):
    """Recovery strategy for node failure"""
    REPLICA_FALLBACK = "replica_fallback"
    MULTI_AZ = "multi_az"
    STATELESS = "stateless"
    BACKUP_FALLBACK = "backup_fallback"
    GENERIC = "generic"


class MonitoringState(str, Enum):
    """Monitoring state from observability platform"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class RecoveryRules(BaseModel):
    """Recovery rules for a node"""
    replica_edge: Optional[str] = Field(None, description="Edge type for replica")
    backup_edge: Optional[str] = Field(None, description="Edge type for backup")
    fallback_rto_multiplier: float = Field(1.0, description="RTO multiplier if fallback")
    circuit_breaker_threshold_seconds: Optional[int] = Field(None, description="Circuit breaker threshold")


class EnhancedInfraNode(BaseModel):
    """Infrastructure node with recovery strategy and monitoring state"""
    id: str
    name: str
    type: str
    rto_minutes: float
    rpo_minutes: float
    recovery_strategy: RecoveryStrategy
    recovery_rules: Optional[RecoveryRules] = None
    monitoring_state: MonitoringState = MonitoringState.UNKNOWN
    observed_latency_ms: Optional[int] = None

    model_config = ConfigDict(use_enum_values=False)


class EnhancedAffectedNode(BaseModel):
    """Affected node in disaster simulation with effective RTO/RPO and cost estimate"""
    id: str
    name: str
    type: str
    distance: int
    step_time_ms: int
    estimated_rto_minutes: float
    estimated_rpo_minutes: float
    effective_rto_minutes: float
    effective_rpo_minutes: float
    recovery_strategy: RecoveryStrategy
    monitoring_state: MonitoringState
    at_risk: bool = False
    # Cost estimation fields
    hourly_cost_usd: Optional[float] = None
    recovery_cost_usd: Optional[float] = None
    region: Optional[str] = None

    model_config = ConfigDict(use_enum_values=False)


class TimelineStep(BaseModel):
    """Single step in disaster timeline"""
    node_id: str
    node_name: str
    distance: int
    step_time_ms: int
    rto_minutes: float
    rpo_minutes: float


class EnhancedSimulationWithTimeline(BaseModel):
    """Complete simulation response with timeline and cost estimates"""
    origin_node_id: str
    blast_radius: List[EnhancedAffectedNode]
    timeline_steps: List[TimelineStep]
    max_distance: int
    total_duration_ms: int
    worst_case_rto_minutes: float
    worst_case_rpo_minutes: float
    model_version: str = "1.0-accurate"
    validation_score: Optional[float] = None
    # Aggregated cost across all affected nodes
    total_recovery_cost_usd: Optional[float] = None
