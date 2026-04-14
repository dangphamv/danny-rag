import asyncio
import logging
import tempfile
from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from langfuse import propagate_attributes
from pydantic import BaseModel
from qdrant_client.http.exceptions import UnexpectedResponse

from src.config import get_settings
from src.ingestion.loaders import SUPPORTED_SUFFIXES
from src.ingestion.pipeline import IngestionResult, ingest_document
from src.limits import limiter
from src.observability.langfuse import get_langfuse
from src.retrieval.dense import qdrant_client
from src.security import require_api_key

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

# MTC-08: 5/min/IP. Read once at import for the decorator literal.
INGEST_RATE_LIMIT = get_settings().ingest_rate_limit


@lru_cache(maxsize=1)
def _get_ingest_semaphore() -> asyncio.Semaphore:
    # MTC-09: cap concurrent ingestion jobs. Lazy so the semaphore binds to the
    # running event loop on first request, not at module import.
    return asyncio.Semaphore(get_settings().ingest_max_concurrent)


def _validate_mime_or_extension(upload: UploadFile, allowed_mimes: tuple[str, ...]) -> None:
    """MTC-09: MIME allowlist with extension fallback.

    Browser-supplied content_type is unreliable, so we accept either an explicit
    MIME match OR a known-good file extension. The loader is the final gate
    (it raises ValueError on unsupported suffixes).
    """
    if upload.content_type and upload.content_type in allowed_mimes:
        return
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix and suffix in SUPPORTED_SUFFIXES:
        return
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=(
            f"Unsupported file type: content_type={upload.content_type!r} "
            f"suffix={suffix!r}. Allowed MIME: {sorted(allowed_mimes)}"
        ),
    )


async def _save_upload_with_cap(upload: UploadFile, max_bytes: int) -> Path:
    """MTC-09: stream the upload to a temp file, aborting if it exceeds the cap.

    Reading in chunks means we never hold the whole upload in memory and we
    abort early on oversized files instead of buffering them first.
    """
    suffix = Path(upload.filename or "").suffix
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="ingest_")
    path = Path(name)
    written = 0
    try:
        with open(fd, "wb") as f:
            while True:
                chunk = await upload.read(64 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"file exceeds {max_bytes} bytes",
                    )
                f.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


class IngestResponse(BaseModel):
    filename: str
    doc_id: str
    total_chunks: int
    upserted: int
    skipped_unchanged: int


class CorpusDocument(BaseModel):
    doc_id: str
    title: str
    source_uri: str
    chunk_count: int
    embedding_model: str
    first_ingested_at: str
    last_ingested_at: str


class CorpusListResponse(BaseModel):
    collection: str
    total_chunks: int
    documents: list[CorpusDocument]


@router.get("/list", response_model=CorpusListResponse)
async def list_corpus(
    request: Request,  # required by slowapi shape consistency
    _: None = Depends(require_api_key),  # MTC-07
) -> CorpusListResponse:
    """Aggregate Qdrant points by doc_id and return per-document summary.

    Powers the "Currently in corpus" panel on the /ingest page. Scrolls the
    whole collection — fine for hobby scale (≤500k chunks). For larger
    corpora this should switch to a payload-index aggregation query.
    """
    settings = get_settings()
    collected: dict[str, dict] = {}
    total = 0

    try:
        async with qdrant_client() as client:
            offset = None
            while True:
                points, offset = await client.scroll(
                    collection_name=settings.qdrant_collection,
                    limit=1000,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    doc_id = str(payload.get("doc_id", ""))
                    if not doc_id:
                        continue
                    total += 1
                    ingested_at = str(payload.get("ingested_at", ""))
                    if doc_id not in collected:
                        collected[doc_id] = {
                            "doc_id": doc_id,
                            "title": str(payload.get("title", "")),
                            "source_uri": str(payload.get("source_uri", "")),
                            "embedding_model": str(payload.get("embedding_model", "")),
                            "chunk_count": 0,
                            "first_ingested_at": ingested_at,
                            "last_ingested_at": ingested_at,
                        }
                    doc = collected[doc_id]
                    doc["chunk_count"] += 1
                    if ingested_at and ingested_at < doc["first_ingested_at"]:
                        doc["first_ingested_at"] = ingested_at
                    if ingested_at and ingested_at > doc["last_ingested_at"]:
                        doc["last_ingested_at"] = ingested_at
                if offset is None:
                    break
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            # Collection doesn't exist yet — empty corpus, return empty list.
            return CorpusListResponse(
                collection=settings.qdrant_collection,
                total_chunks=0,
                documents=[],
            )
        raise

    documents = sorted(
        collected.values(),
        key=lambda d: d["last_ingested_at"],
        reverse=True,
    )
    return CorpusListResponse(
        collection=settings.qdrant_collection,
        total_chunks=total,
        documents=[CorpusDocument(**d) for d in documents],
    )


@router.post("", response_model=IngestResponse)
@limiter.limit(INGEST_RATE_LIMIT)  # MTC-08: 5/min/IP
async def ingest(
    request: Request,  # required by slowapi
    file: Annotated[UploadFile, File(...)],
    _: None = Depends(require_api_key),  # MTC-07
) -> IngestResponse:
    settings = get_settings()
    log.info(
        "ingest upload filename=%r content_type=%r",
        file.filename,
        file.content_type,
    )

    _validate_mime_or_extension(file, settings.upload_allowed_mime_types)
    tmp_path = await _save_upload_with_cap(file, settings.upload_max_bytes)

    # Pass the original filename through so the chunk metadata stores the
    # human-readable name instead of the temp path. The `upload://` prefix on
    # source_uri makes uploads distinguishable from CLI ingests AND keeps doc_id
    # stable across re-uploads of the same filename — which restores MTC-02
    # idempotency for the HTTP path.
    original_name = file.filename or "unknown"
    upload_uri = f"upload://{original_name}"

    lf = get_langfuse()
    try:
        async with _get_ingest_semaphore():  # MTC-09: max 2 concurrent
            # Root Langfuse span for the upload. Any @observe-wrapped work
            # (enrichment, embedding, LLM calls) nests under this observation
            # so per-ingest cost and spans land in a single trace. Mirrors the
            # chat.py pattern at routes/chat.py:51-65.
            with ExitStack() as stack:
                obs = None
                if lf is not None:
                    obs = stack.enter_context(
                        lf.start_as_current_observation(
                            name="ingest.upload",
                            input={
                                "filename": original_name,
                                "content_type": file.content_type,
                                "size_bytes": tmp_path.stat().st_size,
                            },
                        )
                    )
                    stack.enter_context(
                        propagate_attributes(
                            tags=[settings.env, "ingest"],
                        )
                    )
                try:
                    result: IngestionResult = await asyncio.wait_for(
                        ingest_document(
                            tmp_path,
                            source_uri=upload_uri,
                            title=original_name,
                        ),
                        timeout=settings.ingest_timeout_seconds,
                    )
                except TimeoutError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_408_REQUEST_TIMEOUT,
                        detail=f"ingestion exceeded {settings.ingest_timeout_seconds}s",
                    ) from exc
                except ValueError as exc:
                    # loaders.py raises ValueError on unsupported suffix or empty content
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=str(exc),
                    ) from exc
                if obs is not None:
                    try:
                        obs.update(
                            output={
                                "doc_id": result.doc_id,
                                "total_chunks": result.total_chunks,
                                "upserted": result.upserted,
                                "skipped_unchanged": result.skipped_unchanged,
                            }
                        )
                    except Exception as exc:
                        log.debug("langfuse observation.update failed: %s", exc)
    finally:
        tmp_path.unlink(missing_ok=True)

    return IngestResponse(
        filename=file.filename or "",
        doc_id=result.doc_id,
        total_chunks=result.total_chunks,
        upserted=result.upserted,
        skipped_unchanged=result.skipped_unchanged,
    )
