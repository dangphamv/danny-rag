"""LLM-driven ingestion enrichment (ADR-0011).

For each chunk, the configured chat LLM produces a structured JSON payload
containing a summary, hypothetical questions, keywords, entities, and a
cleaned text variant. The enriched fields are embedded alongside the raw
text to widen semantic recall without breaking idempotency — `content_hash`
still hashes only the raw chunk, so repeated ingests remain zero-upsert.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langfuse import observe

from src.ingestion.chunker import Chunk
from src.llm.protocol import LLMProvider, Message

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You enrich document chunks for a retrieval index. Given a chunk, return a "
    "SINGLE JSON object — no prose, no code fences — with these exact keys:\n"
    '  "summary": one short sentence (<25 words) capturing the chunk.\n'
    '  "questions": 3 to 5 distinct questions this chunk can answer verbatim.\n'
    '  "keywords": 3 to 10 lowercase topical keywords.\n'
    '  "entities": named entities present (people, orgs, products, places); empty list if none.\n'
    '  "cleaned_text": the chunk rewritten with OCR artifacts, stray whitespace, and HTML residue removed. '
    "Preserve all facts. Do NOT summarize; do NOT paraphrase.\n"
    "Output valid JSON only."
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _coerce_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    out = [str(v).strip() for v in value if str(v).strip()]
    return out or None


def _parse_enrichment(raw: str) -> dict[str, Any] | None:
    """Parse an LLM response into an enrichment dict. Returns None on any failure."""
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if match is None:
        return None
    try:
        return json.loads(match.group(0))  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return None


async def _enrich_one(
    chunk: Chunk,
    *,
    llm: LLMProvider,
    version: str,
    max_tokens: int,
    sem: asyncio.Semaphore,
) -> Chunk:
    async with sem:
        messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": chunk.text},
        ]
        try:
            raw = await llm.generate(messages, max_tokens=max_tokens)
        except Exception as exc:
            log.warning(
                "enrichment LLM call failed doc_id=%s chunk_index=%d err=%s",
                chunk.doc_id,
                chunk.chunk_index,
                exc,
            )
            return chunk

    parsed = _parse_enrichment(raw)
    if parsed is None:
        log.warning(
            "enrichment JSON parse failed doc_id=%s chunk_index=%d raw=%r",
            chunk.doc_id,
            chunk.chunk_index,
            raw[:400],
        )
        return chunk

    summary = parsed.get("summary")
    cleaned = parsed.get("cleaned_text")
    return chunk.with_enrichment(
        summary=str(summary).strip() if isinstance(summary, str) and summary.strip() else None,
        questions=_coerce_str_list(parsed.get("questions")),
        keywords=_coerce_str_list(parsed.get("keywords")),
        entities=_coerce_str_list(parsed.get("entities")),
        cleaned_text=str(cleaned).strip() if isinstance(cleaned, str) and cleaned.strip() else None,
        version=version,
    )


@observe(name="ingest.enrich")
async def enrich_chunks(
    chunks: list[Chunk],
    *,
    llm: LLMProvider,
    version: str,
    concurrency: int,
    max_tokens: int,
) -> list[Chunk]:
    """Run LLM enrichment on every chunk. Failures fall back to the raw chunk."""
    if not chunks:
        return chunks
    sem = asyncio.Semaphore(max(1, concurrency))
    log.info(
        "enrich start count=%d version=%s concurrency=%d model=%s",
        len(chunks),
        version,
        concurrency,
        llm.model_name,
    )
    results = await asyncio.gather(
        *(
            _enrich_one(c, llm=llm, version=version, max_tokens=max_tokens, sem=sem)
            for c in chunks
        )
    )
    enriched_count = sum(1 for c in results if c.enrichment_version is not None)
    log.info("enrich done enriched=%d fallback=%d", enriched_count, len(results) - enriched_count)
    return list(results)
