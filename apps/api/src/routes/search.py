import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.retrieval.dense import dense_search
from src.retrieval.hybrid import hybrid_search
from src.retrieval.rerank import rerank as rerank_chunks
from src.retrieval.types import ScoredChunk
from src.security import require_api_key

log = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


class SearchResponse(BaseModel):
    query: str
    stage: str
    count: int
    results: list[ScoredChunk]


@router.get("", response_model=SearchResponse)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=1000, description="Query text")],
    top_k: Annotated[int, Query(ge=1, le=50, description="Final result count")] = 5,
    fan_out: Annotated[int, Query(ge=1, le=200, description="Pre-rerank candidate pool")] = 50,
    hybrid: Annotated[bool, Query(description="Use BM25+dense+RRF (default) vs dense-only")] = True,
    rerank: Annotated[bool, Query(description="Apply cross-encoder rerank (default true)")] = True,
    _: None = Depends(require_api_key),
) -> SearchResponse:
    log.info("search q=%r top_k=%d fan_out=%d hybrid=%s rerank=%s", q, top_k, fan_out, hybrid, rerank)

    if hybrid:
        candidates = await hybrid_search(q, top_k=fan_out)
        stage_path = ["hybrid"]
    else:
        candidates = await dense_search(q, top_k=fan_out)
        stage_path = ["dense"]

    if rerank and candidates:
        results = await rerank_chunks(q, candidates, top_k=top_k)
        stage_path.append("rerank")
    else:
        results = candidates[:top_k]

    return SearchResponse(
        query=q,
        stage="+".join(stage_path),
        count=len(results),
        results=results,
    )
