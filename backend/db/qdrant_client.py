"""Qdrant async client wrapper — manages the dr_docs collection."""
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

log = structlog.get_logger()

COLLECTION = "dr_docs"
VECTOR_SIZE = 768  # nomic-embed-text output dimension


class QdrantClient:
    def __init__(self, settings):
        self._url = settings.qdrant_url
        self._client: AsyncQdrantClient | None = None

    async def connect(self):
        self._client = AsyncQdrantClient(url=self._url)
        await self._ensure_collection()
        log.info("qdrant.connected", url=self._url)

    async def _ensure_collection(self):
        existing = await self._client.get_collections()
        names = [c.name for c in existing.collections]
        if COLLECTION not in names:
            await self._client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            log.info("qdrant.collection_created", name=COLLECTION)

    async def upsert(self, points: list[PointStruct]) -> None:
        await self._client.upsert(collection_name=COLLECTION, points=points, wait=True)

    async def search(self, vector: list[float], limit: int = 5) -> list[dict]:
        results = await self._client.search(
            collection_name=COLLECTION,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
        return [{"id": r.id, "score": r.score, "payload": r.payload} for r in results]

    async def close(self):
        if self._client:
            await self._client.close()
