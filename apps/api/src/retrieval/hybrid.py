import asyncio

from src.retrieval.dense import dense_search
from src.retrieval.sparse import sparse_search
from src.retrieval.types import ScoredChunk

# Reciprocal Rank Fusion constant — BRD-01 §3.7 MTC-03 fixes this at 60.
RRF_K = 60


def rrf_fuse(
    dense: list[ScoredChunk],
    sparse: list[ScoredChunk],
    *,
    k: int = RRF_K,
) -> list[ScoredChunk]:
    fused_scores: dict[str, float] = {}
    chunks: dict[str, ScoredChunk] = {}

    for rank, chunk in enumerate(dense):
        contribution = 1.0 / (k + rank + 1)
        fused_scores[chunk.point_id] = fused_scores.get(chunk.point_id, 0.0) + contribution
        chunks.setdefault(chunk.point_id, chunk)

    for rank, chunk in enumerate(sparse):
        contribution = 1.0 / (k + rank + 1)
        fused_scores[chunk.point_id] = fused_scores.get(chunk.point_id, 0.0) + contribution
        chunks.setdefault(chunk.point_id, chunk)

    ordered = sorted(fused_scores.items(), key=lambda item: -item[1])
    return [chunks[pid].with_score(score) for pid, score in ordered]


async def hybrid_search(query: str, top_k: int = 50) -> list[ScoredChunk]:
    """Run dense + BM25 in parallel, fuse with RRF (k=60). MTC-03."""
    dense_results, sparse_results = await asyncio.gather(
        dense_search(query, top_k=top_k),
        sparse_search(query, top_k=top_k),
    )
    fused = rrf_fuse(dense_results, sparse_results)
    return fused[:top_k]
