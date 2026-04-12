import asyncio
import logging
from functools import lru_cache

from sentence_transformers import CrossEncoder

from src.retrieval.types import ScoredChunk

log = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-base"


class CrossEncoderReranker:
    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL) -> None:
        log.info("loading cross-encoder model=%s", model_name)
        self._model = CrossEncoder(model_name)
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def _rerank_sync(
        self,
        query: str,
        chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[ScoredChunk]:
        if not chunks:
            return []
        pairs = [(query, c.text) for c in chunks]
        scores = self._model.predict(pairs)
        scored = sorted(
            zip(chunks, scores, strict=True),
            key=lambda x: -float(x[1]),
        )[:top_k]
        return [chunk.with_score(float(score)) for chunk, score in scored]

    async def rerank(
        self,
        query: str,
        chunks: list[ScoredChunk],
        top_k: int = 5,
    ) -> list[ScoredChunk]:
        # CrossEncoder.predict is synchronous and CPU-bound; offload to a thread
        # so the event loop stays free for streaming responses.
        return await asyncio.to_thread(self._rerank_sync, query, chunks, top_k)


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker()


async def rerank(query: str, chunks: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
    return await get_reranker().rerank(query, chunks, top_k=top_k)
