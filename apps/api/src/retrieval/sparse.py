import asyncio
import logging
import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

from src.config import get_settings
from src.retrieval.dense import qdrant_client
from src.retrieval.types import ScoredChunk

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Index:
    """In-memory BM25 index built lazily from the live Qdrant collection.

    Invalidated by `pipeline.ingest_document` after every successful upsert
    so the next query rebuilds against fresh data.
    """

    def __init__(self) -> None:
        self._index: BM25Okapi | None = None
        self._docs: list[ScoredChunk] = []
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._index = None
        self._docs = []

    async def _build(self) -> None:
        settings = get_settings()
        async with qdrant_client() as client:
            collected: list[ScoredChunk] = []
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
                    collected.append(
                        ScoredChunk.from_payload(
                            point_id=str(point.id),
                            payload=point.payload,
                            score=0.0,
                        )
                    )
                if offset is None:
                    break
        self._docs = collected
        if not collected:
            # BM25Okapi requires at least one document. We construct a placeholder
            # so `_index is None` doesn't fire on the next call (which would loop
            # us back into _build for no reason). `search()` short-circuits on
            # empty `_docs` before ever querying this index.
            log.warning("BM25 index built from empty collection")
            self._index = BM25Okapi([[""]])
            return
        tokenized = [_tokenize(d.text) for d in collected]
        self._index = BM25Okapi(tokenized)
        log.info("BM25 index built docs=%d", len(collected))

    async def search(self, query: str, top_k: int = 50) -> list[ScoredChunk]:
        async with self._lock:
            if self._index is None:
                await self._build()
        assert self._index is not None
        if not self._docs:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._index.get_scores(tokens)
        ranked = sorted(
            ((i, float(s)) for i, s in enumerate(scores) if s > 0),
            key=lambda x: -x[1],
        )[:top_k]
        return [self._docs[i].with_score(score) for i, score in ranked]


@lru_cache(maxsize=1)
def get_bm25_index() -> BM25Index:
    return BM25Index()


def invalidate_bm25_cache() -> None:
    get_bm25_index().invalidate()


async def sparse_search(query: str, top_k: int = 50) -> list[ScoredChunk]:
    return await get_bm25_index().search(query, top_k=top_k)
