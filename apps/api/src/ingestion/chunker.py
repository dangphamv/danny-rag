import hashlib
from datetime import UTC, datetime
from uuid import NAMESPACE_DNS, UUID, uuid5

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, ConfigDict, Field

# MTC-02: deterministic UUIDv5 namespace so the same (doc_id, chunk_index)
# pair always maps to the same Qdrant point ID across runs.
CHUNK_NAMESPACE: UUID = uuid5(NAMESPACE_DNS, "danny_rag.chunks")

CHUNK_SIZE = 512  # tokens (cl100k_base via tiktoken)
CHUNK_OVERLAP = 64
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    chunk_index: int
    text: str
    content_hash: str
    source_uri: str
    title: str
    page: int | None = None
    section: str | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    embedding_model: str

    # ADR-0011: optional LLM-generated enrichment. content_hash still hashes
    # only the raw `text`, so LLM output drift can never break MTC-02.
    enriched_summary: str | None = None
    enriched_questions: list[str] | None = None
    enriched_keywords: list[str] | None = None
    enriched_entities: list[str] | None = None
    enriched_cleaned_text: str | None = None
    enrichment_version: str | None = None

    @property
    def point_id(self) -> str:
        return str(uuid5(CHUNK_NAMESPACE, f"{self.doc_id}:{self.chunk_index}"))

    def embed_text(self) -> str:
        """Text fed to the embedder. Falls back to raw text when enrichment is absent."""
        if self.enrichment_version is None:
            return self.text
        parts: list[str] = []
        if self.enriched_summary:
            parts.append(self.enriched_summary)
        if self.enriched_questions:
            questions = "\n".join(f"- {q}" for q in self.enriched_questions)
            parts.append(f"Questions this answers:\n{questions}")
        tags: list[str] = []
        if self.enriched_keywords:
            tags.append("Keywords: " + ", ".join(self.enriched_keywords))
        if self.enriched_entities:
            tags.append("Entities: " + ", ".join(self.enriched_entities))
        if tags:
            parts.append("\n".join(tags))
        parts.append(self.enriched_cleaned_text or self.text)
        return "\n\n".join(parts)

    def with_enrichment(
        self,
        *,
        summary: str | None,
        questions: list[str] | None,
        keywords: list[str] | None,
        entities: list[str] | None,
        cleaned_text: str | None,
        version: str,
    ) -> "Chunk":
        """Return a new frozen Chunk carrying enrichment output."""
        return self.model_copy(
            update={
                "enriched_summary": summary,
                "enriched_questions": questions,
                "enriched_keywords": keywords,
                "enriched_entities": entities,
                "enriched_cleaned_text": cleaned_text,
                "enrichment_version": version,
            }
        )

    def payload(self) -> dict[str, object]:
        # Stored alongside the vector in Qdrant.
        data: dict[str, object] = {
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "content_hash": self.content_hash,
            "source_uri": self.source_uri,
            "title": self.title,
            "page": self.page,
            "section": self.section,
            "ingested_at": self.ingested_at.isoformat(),
            "embedding_model": self.embedding_model,
        }
        if self.enrichment_version is not None:
            data["enrichment_version"] = self.enrichment_version
            data["enriched_summary"] = self.enriched_summary
            data["enriched_questions"] = self.enriched_questions
            data["enriched_keywords"] = self.enriched_keywords
            data["enriched_entities"] = self.enriched_entities
            data["enriched_cleaned_text"] = self.enriched_cleaned_text
        return data


def derive_doc_id(source_uri: str) -> str:
    return hashlib.sha256(source_uri.encode("utf-8")).hexdigest()[:16]


def chunk_document(
    text: str,
    *,
    doc_id: str,
    source_uri: str,
    title: str,
    embedding_model: str,
) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=SEPARATORS,
    )
    pieces = splitter.split_text(text)
    chunks: list[Chunk] = []
    for i, piece in enumerate(pieces):
        cleaned = piece.strip()
        if not cleaned:
            continue
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_index=i,
                text=cleaned,
                content_hash=hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
                source_uri=source_uri,
                title=title,
                embedding_model=embedding_model,
            )
        )
    return chunks
