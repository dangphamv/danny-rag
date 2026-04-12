import logging
from pathlib import Path

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from src.config import get_settings
from src.ingestion.chunker import Chunk, chunk_document, derive_doc_id
from src.ingestion.loaders import load_document
from src.llm.factory import get_embedder
from src.retrieval.sparse import invalidate_bm25_cache

log = logging.getLogger(__name__)


class IngestionResult(BaseModel):
    doc_id: str
    source_uri: str
    total_chunks: int
    upserted: int
    skipped_unchanged: int


def get_qdrant_client() -> AsyncQdrantClient:
    settings = get_settings()
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key)


async def ensure_collection(client: AsyncQdrantClient) -> None:
    settings = get_settings()
    name = settings.qdrant_collection
    existing = await client.get_collections()
    if any(c.name == name for c in existing.collections):
        return
    log.info(
        "creating qdrant collection name=%s dim=%d distance=cosine",
        name,
        settings.embedding_dimension,
    )
    await client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=settings.embedding_dimension,
            distance=Distance.COSINE,
        ),
    )


async def ingest_document(
    path: Path,
    *,
    source_uri: str | None = None,
    title: str | None = None,
) -> IngestionResult:
    """Ingest a document on disk into the configured Qdrant collection.

    `path` is the on-disk location to read from. `source_uri` and `title`
    override the metadata stored in chunk payloads — needed for HTTP uploads
    so the temp file path doesn't leak into the corpus. Defaults preserve the
    CLI behavior (source_uri = absolute path, title = file basename).
    """
    settings = get_settings()
    final_source_uri = source_uri or str(path.resolve())
    final_title = title or path.name
    doc_id = derive_doc_id(final_source_uri)
    log.info(
        "ingest start source_uri=%s title=%r doc_id=%s",
        final_source_uri,
        final_title,
        doc_id,
    )

    text = load_document(path)
    if not text.strip():
        raise ValueError(f"Loaded empty content from {final_title}")

    embedder = get_embedder()
    chunks: list[Chunk] = chunk_document(
        text,
        doc_id=doc_id,
        source_uri=final_source_uri,
        title=final_title,
        embedding_model=embedder.model_name,
    )
    log.info("chunked count=%d", len(chunks))

    if embedder.dimension != settings.embedding_dimension:
        # MTC-01 / MTC-11 sanity: never let a wrong-dim embedder write to the wrong collection.
        raise RuntimeError(
            f"Embedder dim {embedder.dimension} does not match settings dim "
            f"{settings.embedding_dimension}; refusing to upsert"
        )

    client = get_qdrant_client()
    try:
        await ensure_collection(client)

        # MTC-02: idempotency. Fetch existing points by ID and compare content_hash.
        point_ids = [c.point_id for c in chunks]
        existing = await client.retrieve(
            collection_name=settings.qdrant_collection,
            ids=point_ids,
            with_payload=["content_hash"],
            with_vectors=False,
        )
        existing_hashes = {
            str(p.id): (p.payload or {}).get("content_hash")
            for p in existing
        }

        to_upsert: list[Chunk] = [
            c for c in chunks if existing_hashes.get(c.point_id) != c.content_hash
        ]
        skipped = len(chunks) - len(to_upsert)

        if to_upsert:
            vectors = await embedder.embed_batch([c.text for c in to_upsert])
            points = [
                PointStruct(id=c.point_id, vector=v, payload=c.payload())
                for c, v in zip(to_upsert, vectors, strict=True)
            ]
            await client.upsert(
                collection_name=settings.qdrant_collection,
                points=points,
                wait=True,
            )
            invalidate_bm25_cache()
            log.info("upserted count=%d skipped_unchanged=%d", len(to_upsert), skipped)
        else:
            log.info("nothing to upsert — all chunks unchanged (idempotent)")

        return IngestionResult(
            doc_id=doc_id,
            source_uri=final_source_uri,
            total_chunks=len(chunks),
            upserted=len(to_upsert),
            skipped_unchanged=skipped,
        )
    finally:
        await client.close()
