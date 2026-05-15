"""
FastAPI dependency injection utilities for validation, auth, and rate limiting.
"""
from typing import Optional
from fastapi import Header, HTTPException, Request, status
import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address

log = structlog.get_logger()

# Shared rate limiter instance
limiter = Limiter(key_func=get_remote_address)


async def verify_node_exists(node_id: str, neo4j_client) -> None:
    """
    Verify that a node exists in Neo4j.
    Raises 404 if not found.
    """
    result = await neo4j_client.run(
        "MATCH (n:InfraNode {id: $id}) RETURN n.id LIMIT 1",
        {"id": node_id},
    )
    if not result:
        log.warning("node_not_found", node_id=node_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found in graph",
        )


async def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    settings = None,
) -> Optional[str]:
    """
    Verify API key authentication if enabled.

    If API_SECRET_KEY env var is set, all requests must include X-API-Key header.
    If not set, authentication is bypassed (development mode).

    Returns the API key if valid, None if auth disabled.
    Raises 403 if auth enabled but key is invalid.
    """
    # If no secret key is configured, auth is disabled
    if not settings or not settings.api_secret_key:
        return None

    # Auth is enabled: check for X-API-Key header
    if not x_api_key:
        log.warning("api_key_missing", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-API-Key header",
        )

    # Verify key matches configured secret
    if x_api_key != settings.api_secret_key:
        log.warning("api_key_invalid", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return x_api_key
