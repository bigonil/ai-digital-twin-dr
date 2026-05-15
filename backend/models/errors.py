"""
Unified error response schema for API endpoints.
"""
from datetime import datetime
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response format."""
    error: str  # Error code/type (e.g., 'NODE_NOT_FOUND', 'VALIDATION_ERROR', 'INTERNAL_ERROR')
    message: str  # Human-readable error message
    timestamp: str  # ISO 8601 timestamp when error occurred
    request_id: str  # Request ID for tracking/debugging

    class Config:
        json_schema_extra = {
            "example": {
                "error": "NODE_NOT_FOUND",
                "message": "Node 'db-001' not found in graph",
                "timestamp": "2026-05-14T10:30:00Z",
                "request_id": "req_a1b2c3d4",
            }
        }
