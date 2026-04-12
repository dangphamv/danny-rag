from typing import TypedDict

from pydantic import BaseModel

from src.retrieval.types import ScoredChunk


class Citation(BaseModel):
    doc_id: str
    chunk_index: int
    title: str
    source_uri: str
    page: int | None = None
    snippet: str
    score: float


class GraphState(TypedDict, total=False):
    # Input
    question: str
    session_id: str

    # Intermediate
    rewritten_question: str
    candidates: list[ScoredChunk]
    reranked: list[ScoredChunk]

    # Output
    answer: str
    citations: list[Citation]

    # Loop guard for M10 self-grading. Initialized to 0; bumped on rewrite.
    rewrite_count: int
    grounding_score: float | None
