"""
Phase 3 — Documentation ingestion pipeline.
Splits Markdown files into chunks, embeds via Ollama nomic-embed-text,
upserts into Qdrant and links Document nodes to Neo4j InfraNodes.
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import httpx
import structlog
from qdrant_client.models import PointStruct

from settings import Settings

log = structlog.get_logger()
settings = Settings()

CHUNK_SIZE = 512   # characters
CHUNK_OVERLAP = 64

# Singleton httpx client for Ollama embeddings
_ollama_client: httpx.AsyncClient | None = None
# Embedding cache: text → vector
_embed_cache: dict[str, list[float]] = {}


@lru_cache(maxsize=256)
def _chunk_text(text: str) -> tuple[str, ...]:
    """Chunk text with overlap. Cached for repeated ingestions."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return tuple(c.strip() for c in chunks if c.strip())


def _doc_id(file_path: str, chunk_idx: int) -> str:
    raw = f"{file_path}::{chunk_idx}"
    return str(UUID(hashlib.md5(raw.encode()).hexdigest()))


async def _get_ollama_client() -> httpx.AsyncClient:
    """Get or create singleton httpx client for Ollama."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = httpx.AsyncClient(timeout=60)
    return _ollama_client


async def _embed(text: str) -> list[float]:
    """Embed text using Ollama. Results are cached in-memory."""
    # Check cache first
    if text in _embed_cache:
        return _embed_cache[text]

    # Call Ollama embedding API
    client = await _get_ollama_client()
    resp = await client.post(
        f"{settings.ollama_base_url}/api/embeddings",
        json={"model": settings.ollama_embed_model, "prompt": text},
    )
    resp.raise_for_status()
    vector = resp.json()["embedding"]

    # Cache result
    _embed_cache[text] = vector
    return vector


async def ingest(docs_dir: str | Path, qdrant_client, neo4j_client=None) -> dict[str, int]:
    base = Path(docs_dir)
    total_points = 0
    total_nodes = 0

    md_files = list(base.rglob("*.md"))
    log.info("docs.ingest_start", directory=str(base), file_count=len(md_files))

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        chunks = list(_chunk_text(text))  # Convert tuple to list for indexing
        rel_path = str(md_file.relative_to(base))

        points = []
        for idx, chunk in enumerate(chunks):
            try:
                vector = await _embed(chunk)
            except Exception as exc:
                log.warning("docs.embed_error", file=rel_path, chunk=idx, error=str(exc))
                continue

            doc_id = _doc_id(rel_path, idx)
            points.append(PointStruct(
                id=doc_id,
                vector=vector,
                payload={
                    "text": chunk,
                    "source_file": rel_path,
                    "chunk_index": idx,
                    "title": md_file.stem,
                },
            ))

        if points:
            await qdrant_client.upsert(points=points)
            total_points += len(points)

        # Optionally create a Document node in Neo4j
        if neo4j_client:
            doc_node_id = hashlib.md5(rel_path.encode()).hexdigest()[:12]
            await neo4j_client.merge_node(
                {
                    "id": doc_node_id,
                    "name": md_file.stem,
                    "type": "Document",
                    "source_file": rel_path,
                },
                label="Document",
            )
            total_nodes += 1

    log.info("docs.ingest_done", qdrant_points=total_points, neo4j_nodes=total_nodes)
    return {"qdrant_points": total_points, "neo4j_nodes": total_nodes}
