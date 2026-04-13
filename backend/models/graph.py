from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class InfraEdge(BaseModel):
    source: str
    target: str
    type: str
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)


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


class DisasterSimulationResult(BaseModel):
    origin_node_id: str
    blast_radius: list[AffectedNode]
    total_affected: int
    worst_case_rto_minutes: int | None = None
    worst_case_rpo_minutes: int | None = None
    recovery_steps: list[str] = Field(default_factory=list)


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
