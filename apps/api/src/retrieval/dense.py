from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from qdrant_client import AsyncQdrantClient

from src.config import get_settings
from src.llm.factory import get_embedder
from src.retrieval.types import ScoredChunk


@asynccontextmanager
async def qdrant_client() -> AsyncIterator[AsyncQdrantClient]:
    settings = get_settings()
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key)
    try:
        yield client
    finally:
        await client.close()


async def dense_search(query: str, top_k: int = 50) -> list[ScoredChunk]:
    settings = get_settings()
    embedder = get_embedder()
    query_vec = (await embedder.embed_batch([query]))[0]
    async with qdrant_client() as client:
        response = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vec,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return [
            ScoredChunk.from_payload(
                point_id=str(point.id),
                payload=point.payload,
                score=float(point.score) if point.score is not None else 0.0,
            )
            for point in response.points
        ]
