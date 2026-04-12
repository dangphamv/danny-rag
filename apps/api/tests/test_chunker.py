from src.ingestion.chunker import (
    CHUNK_NAMESPACE,
    Chunk,
    chunk_document,
    derive_doc_id,
)


def test_derive_doc_id_is_stable() -> None:
    a = derive_doc_id("/tmp/foo.pdf")
    b = derive_doc_id("/tmp/foo.pdf")
    assert a == b
    assert len(a) == 16


def test_derive_doc_id_changes_with_path() -> None:
    assert derive_doc_id("/tmp/foo.pdf") != derive_doc_id("/tmp/bar.pdf")


def test_chunk_document_produces_chunks_with_metadata() -> None:
    text = "Paragraph one.\n\nParagraph two has more content.\n\nThird paragraph here."
    chunks = chunk_document(
        text,
        doc_id="abc123",
        source_uri="/tmp/sample.txt",
        title="sample.txt",
        embedding_model="text-embedding-3-small",
    )
    assert len(chunks) >= 1
    for c in chunks:
        assert c.doc_id == "abc123"
        assert c.source_uri == "/tmp/sample.txt"
        assert c.title == "sample.txt"
        assert c.embedding_model == "text-embedding-3-small"
        assert c.content_hash
        assert len(c.content_hash) == 64  # sha256 hex


def test_chunk_point_id_is_deterministic() -> None:
    text = "Hello world. This is a test."
    chunks_a = chunk_document(
        text, doc_id="x", source_uri="x", title="x", embedding_model="m"
    )
    chunks_b = chunk_document(
        text, doc_id="x", source_uri="x", title="x", embedding_model="m"
    )
    assert [c.point_id for c in chunks_a] == [c.point_id for c in chunks_b]


def test_chunk_point_id_uses_namespace() -> None:
    chunk = Chunk(
        doc_id="d1",
        chunk_index=0,
        text="hello",
        content_hash="0" * 64,
        source_uri="x",
        title="x",
        embedding_model="m",
    )
    # Point ID is a UUIDv5 derived from CHUNK_NAMESPACE — same input, same output.
    from uuid import uuid5

    expected = str(uuid5(CHUNK_NAMESPACE, "d1:0"))
    assert chunk.point_id == expected
