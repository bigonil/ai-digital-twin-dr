from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CloudProvider(str, Enum):
    aws = "aws"
    gcp = "gcp"
    azure = "azure"
    on_prem = "on_prem"
    unknown = "unknown"


class ResourceStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    failed = "failed"
    simulated_failure = "simulated_failure"
    unknown = "unknown"


class InfraNode(BaseModel):
    id: str
    name: str
    type: str
    provider: CloudProvider = CloudProvider.unknown
    region: str | None = None
    az: str | None = None
    status: ResourceStatus = ResourceStatus.unknown
    is_redundant: bool = False
    rto_minutes: int | None = None
    rpo_minutes: int | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)

    @field_validator("provider", mode="before")
    @classmethod
    def _default_provider(cls, v: Any) -> Any:
        return v if v is not None else CloudProvider.unknown

    @field_validator("status", mode="before")
    @classmethod
    def _default_status(cls, v: Any) -> Any:
        return v if v is not None else ResourceStatus.unknown

    @field_validator("is_redundant", mode="before")
    @classmethod
    def _default_is_redundant(cls, v: Any) -> Any:
        return v if v is not None else False


class InfraEdge(BaseModel):
    source: str
    target: str
    type: str = "CONNECTS"
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _default_type(cls, v: Any) -> Any:
        return v if v is not None else "CONNECTS"

    @field_validator("weight", mode="before")
    @classmethod
    def _default_weight(cls, v: Any) -> Any:
        return v if v is not None else 1.0


class InfraGraph(BaseModel):
    nodes: list[InfraNode]
    edges: list[InfraEdge]


class DisasterSimulationRequest(BaseModel):
    node_id: str
    depth: int = Field(default=5, ge=1, le=10)


class AffectedNode(BaseModel):
    id: str
    name: str
    type: str
    distance: int
    estimated_rto_minutes: int | None = None
    estimated_rpo_minutes: int | None = None
    step_time_ms: int = 0


class DisasterSimulationResult(BaseModel):
    origin_node_id: str
    blast_radius: list[AffectedNode]
    total_affected: int
    worst_case_rto_minutes: int | None = None
    worst_case_rpo_minutes: int | None = None
    recovery_steps: list[str] = Field(default_factory=list)


class SimulationWithTimeline(BaseModel):
    """Enhanced disaster simulation result with timeline animation data."""
    origin_node_id: str
    blast_radius: list[AffectedNode]
    total_affected: int
    worst_case_rto_minutes: int | None = None
    worst_case_rpo_minutes: int | None = None
    recovery_steps: list[str] = Field(default_factory=list)

    # Timeline-specific fields
    max_distance: int  # maximum BFS distance in cascade
    total_duration_ms: int  # total animation duration (5000-8000ms)

    # For MCP agents: raw timeline data for programmatic access
    timeline_steps: list[dict] = Field(default_factory=list)  # [{node_id, step_time_ms, distance}, ...]


class DriftResult(BaseModel):
    nodes_in_graph_only: list[str]
    nodes_in_terraform_only: list[str]
    drifted_properties: list[dict[str, Any]]


class HealthStatus(BaseModel):
    node_id: str
    status: ResourceStatus
    cpu_percent: float | None = None
    memory_percent: float | None = None
    replication_lag_seconds: float | None = None
    last_updated: str | None = None
