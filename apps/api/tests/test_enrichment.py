"""Tests for LLM-enriched ingestion (ADR-0011)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from src.ingestion.chunker import Chunk, chunk_document
from src.ingestion.enrichment import _parse_enrichment, enrich_chunks
from src.llm.protocol import Message


class _FakeLLM:
    def __init__(self, response: str, *, delay: float = 0.0) -> None:
        self._response = response
        self._delay = delay
        self.in_flight = 0
        self.peak_in_flight = 0
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "fake-llm"

    async def generate(self, messages: list[Message], max_tokens: int = 1024) -> str:
        self.calls += 1
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            return self._response
        finally:
            self.in_flight -= 1

    def astream(
        self, messages: list[Message], max_tokens: int = 1024
    ) -> AsyncIterator[str]:  # pragma: no cover - unused
        async def _gen() -> AsyncIterator[str]:
            yield self._response

        return _gen()


def _make_chunk(text: str = "Hello world.", index: int = 0) -> Chunk:
    return chunk_document(
        text,
        doc_id="doc-1",
        source_uri="/tmp/sample.txt",
        title="sample.txt",
        embedding_model="text-embedding-3-small",
    )[index]


def test_parse_enrichment_happy_path() -> None:
    raw = (
        '{"summary": "A test chunk.", "questions": ["q1", "q2"], '
        '"keywords": ["alpha"], "entities": [], "cleaned_text": "Cleaned."}'
    )
    parsed = _parse_enrichment(raw)
    assert parsed is not None
    assert parsed["summary"] == "A test chunk."
    assert parsed["questions"] == ["q1", "q2"]


def test_parse_enrichment_extracts_embedded_json() -> None:
    raw = 'prefix text\n{"summary": "ok", "questions": [], "keywords": [], "entities": [], "cleaned_text": "x"}\ntrailing'
    parsed = _parse_enrichment(raw)
    assert parsed is not None
    assert parsed["summary"] == "ok"


def test_parse_enrichment_returns_none_on_garbage() -> None:
    assert _parse_enrichment("this is not json") is None
    assert _parse_enrichment("") is None
    assert _parse_enrichment("   ") is None


@pytest.mark.asyncio
async def test_enrich_chunks_populates_fields() -> None:
    chunk = _make_chunk("The capital of France is Paris.")
    llm = _FakeLLM(
        '{"summary": "Paris is the capital of France.", '
        '"questions": ["What is the capital of France?", "Where is Paris?"], '
        '"keywords": ["france", "paris", "capital"], '
        '"entities": ["France", "Paris"], '
        '"cleaned_text": "The capital of France is Paris."}'
    )
    result = await enrich_chunks(
        [chunk], llm=llm, version="v1", concurrency=2, max_tokens=512
    )
    assert len(result) == 1
    out = result[0]
    assert out.enrichment_version == "v1"
    assert out.enriched_summary == "Paris is the capital of France."
    assert out.enriched_questions == ["What is the capital of France?", "Where is Paris?"]
    assert out.enriched_keywords == ["france", "paris", "capital"]
    assert out.enriched_entities == ["France", "Paris"]
    assert out.content_hash == chunk.content_hash
    assert out.text == chunk.text


@pytest.mark.asyncio
async def test_enrich_chunks_falls_back_on_bad_json() -> None:
    chunk = _make_chunk()
    llm = _FakeLLM("sorry I cannot do that")
    result = await enrich_chunks(
        [chunk], llm=llm, version="v1", concurrency=2, max_tokens=512
    )
    assert len(result) == 1
    assert result[0].enrichment_version is None
    assert result[0].enriched_summary is None
    assert result[0] == chunk


@pytest.mark.asyncio
async def test_enrich_chunks_falls_back_on_llm_exception() -> None:
    class _BoomLLM(_FakeLLM):
        async def generate(self, messages: list[Message], max_tokens: int = 1024) -> str:
            raise RuntimeError("provider down")

    chunk = _make_chunk()
    result = await enrich_chunks(
        [chunk], llm=_BoomLLM(""), version="v1", concurrency=2, max_tokens=512
    )
    assert result[0].enrichment_version is None


@pytest.mark.asyncio
async def test_enrich_chunks_respects_concurrency_limit() -> None:
    chunks = [_make_chunk(f"Chunk number {i}.", index=0) for i in range(10)]
    llm = _FakeLLM(
        '{"summary": "s", "questions": ["q"], "keywords": ["k"], '
        '"entities": [], "cleaned_text": "c"}',
        delay=0.05,
    )
    await enrich_chunks(chunks, llm=llm, version="v1", concurrency=3, max_tokens=512)
    assert llm.calls == 10
    assert llm.peak_in_flight <= 3


def test_embed_text_falls_back_to_raw_without_enrichment() -> None:
    chunk = _make_chunk("Plain chunk.")
    assert chunk.embed_text() == chunk.text


def test_embed_text_assembles_all_enrichment_parts() -> None:
    chunk = _make_chunk("Raw body.").with_enrichment(
        summary="One-line summary.",
        questions=["Q1?", "Q2?"],
        keywords=["alpha", "beta"],
        entities=["Acme"],
        cleaned_text="Cleaned body.",
        version="v1",
    )
    text = chunk.embed_text()
    assert "One-line summary." in text
    assert "Q1?" in text and "Q2?" in text
    assert "Keywords: alpha, beta" in text
    assert "Entities: Acme" in text
    assert "Cleaned body." in text
    assert chunk.content_hash  # still the raw-text hash


def test_embed_text_falls_back_to_raw_when_cleaned_missing() -> None:
    chunk = _make_chunk("Raw body.").with_enrichment(
        summary="s",
        questions=None,
        keywords=None,
        entities=None,
        cleaned_text=None,
        version="v1",
    )
    assert "Raw body." in chunk.embed_text()


def test_payload_includes_enrichment_fields_when_present() -> None:
    chunk = _make_chunk().with_enrichment(
        summary="s",
        questions=["q"],
        keywords=["k"],
        entities=[],
        cleaned_text="c",
        version="v1",
    )
    payload = chunk.payload()
    assert payload["enrichment_version"] == "v1"
    assert payload["enriched_summary"] == "s"
    assert payload["enriched_questions"] == ["q"]


def test_payload_omits_enrichment_fields_when_absent() -> None:
    chunk = _make_chunk()
    payload = chunk.payload()
    assert "enrichment_version" not in payload
    assert "enriched_summary" not in payload
