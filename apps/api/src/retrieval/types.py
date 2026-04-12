from typing import Any

from pydantic import BaseModel


class ScoredChunk(BaseModel):
    point_id: str
    doc_id: str
    chunk_index: int
    text: str
    title: str
    source_uri: str
    page: int | None = None
    score: float = 0.0

    @classmethod
    def from_payload(cls, point_id: str, payload: dict[str, Any] | None, score: float) -> "ScoredChunk":
        p = payload or {}
        return cls(
            point_id=point_id,
            doc_id=str(p.get("doc_id", "")),
            chunk_index=int(p.get("chunk_index", 0)),
            text=str(p.get("text", "")),
            title=str(p.get("title", "")),
            source_uri=str(p.get("source_uri", "")),
            page=p.get("page"),
            score=score,
        )

    def with_score(self, score: float) -> "ScoredChunk":
        return self.model_copy(update={"score": score})
