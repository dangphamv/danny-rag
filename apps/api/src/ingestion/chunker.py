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

    @property
    def point_id(self) -> str:
        return str(uuid5(CHUNK_NAMESPACE, f"{self.doc_id}:{self.chunk_index}"))

    def payload(self) -> dict[str, object]:
        # Stored alongside the vector in Qdrant.
        return {
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
