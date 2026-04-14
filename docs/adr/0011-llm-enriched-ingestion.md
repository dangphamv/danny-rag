# 0011. LLM-driven ingestion enrichment (opt-in, reuse LLM_PROVIDER)

- **Status**: Accepted
- **Date**: 2026-04-14
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3206 (AI/ML), MTC-01, MTC-02, MTC-04, MTC-10

## Context

Classic retrieval embeds raw chunk text directly. When a user's query vocabulary diverges from the source document's vocabulary — technical jargon vs. plain-language questions, acronyms vs. expanded forms, implicit concepts vs. explicit statements — dense similarity fails even when the answer is present. This is especially acute on noisy or long-form corpora (PDFs, scanned docs, meeting notes).

HyDE (Hypothetical Document Embeddings) and related enrichment strategies address this by embedding a richer text representation rather than the raw chunk. Instead of embedding only what the author wrote, we embed what the chunk *means*: a summary, likely questions it answers, its keywords, named entities, and a cleaned-text variant.

The constraints this must respect:

- **MTC-01** — one Qdrant collection per embedding model. The enrichment pipeline feeds into the same embedder; collection schema must not change.
- **MTC-02** — idempotent ingestion. Re-ingesting identical source files must not create new points. `content_hash` is SHA256 of raw chunk text; LLM output drift must not break this guarantee.
- **MTC-04** — grounding contract. Raw source text must remain in the payload for citation display. Only the embedded vector changes; the stored `text` field is never replaced.
- **MTC-10** — 1024-token hard cap in the provider layer. The enrichment LLM call respects this ceiling via `INGEST_ENRICH_MAX_TOKENS`.

BRD-01 §3.7 (Hard Rule #1) requires an ADR before merging any architectural change. This ADR covers the enrichment step added across `config.py`, `chunker.py`, `enrichment.py`, and `pipeline.py`.

## Decision

Add an **opt-in LLM enrichment step** in the ingestion pipeline, controlled by `INGEST_ENRICH=true` (default `false`). When enabled, each new chunk receives one LLM call (via the existing `LLM_PROVIDER` abstraction) that returns a JSON payload containing: `summary`, `hypothetical_questions`, `keywords`, `entities`, and `cleaned_text`. The concatenated enrichment fields are used as the embedded text; the original raw `text` is preserved in the Qdrant payload unchanged.

## Rationale

- **Widens semantic recall** without altering collection schema or embedder. The improvement targets vocabulary-divergence failures, the dominant miss type on noisy corpora.
- **Reusing `LLM_PROVIDER`** avoids a new provider abstraction and a new env knob. The Anthropic/OpenAI/Ollama factory built for `/chat` is exactly what we want — consistent model behavior, cost visibility, and the same rate-limit discipline.
- **Opt-in default-off** means zero impact on existing deployments. The flag can be toggled per-environment without a deploy or migration.
- **`content_hash` isolation** keeps MTC-02 intact. LLM output is non-deterministic; tying idempotency to raw text hash plus a version string (`enrichment_version`) makes re-enrichment explicit and controlled — a version bump, not silent churn.
- **Enrichment after dedupe** ensures unchanged files pay zero LLM cost on re-ingest. The expensive operation only runs on net-new or explicitly re-versioned chunks.
- **Graceful fallback** on JSON parse failure or LLM exception means ingest never blocks. The chunk passes through as raw text with no `enrichment_version` stamp.

## Consequences

### Positive
- Higher retrieval recall on corpora where query vocabulary diverges from source text (HyDE-style embedding of semantic expansions)
- Metadata fields (`keywords`, `entities`) are stored in the Qdrant payload and enable future filtered search without schema changes
- Zero effect on existing deployments — default `INGEST_ENRICH=false`, existing points untouched
- Re-enrichment of a corpus is a one-env-var operation: set `INGEST_ENRICH_VERSION=v2` and re-run ingest; no manual point migration required
- Every enrichment call is traced under `ingest.enrich` in Langfuse via `@observe`, so cost and latency are visible per ingest job

### Negative / Trade-offs
- Adds ~1 LLM call per net-new chunk — cost scales linearly with ingest volume; large initial ingests are meaningfully more expensive
- Enrichment quality is LLM-dependent; parse failures fall back to raw text silently, making enrichment coverage non-trivially observable without Langfuse trace inspection
- Non-determinism in LLM output means two identical source files ingested at different times (different `enrichment_version`) will produce different vectors — expected behavior, but can surprise when debugging retrieval drift
- Toggling `INGEST_ENRICH=true` on an existing corpus requires re-embedding every chunk (cost spike, one-time)

### Neutral / Follow-ups
- A DeepEval ablation comparing `INGEST_ENRICH=true` vs `false` on the same corpus is the correct next step to quantify recall lift; this should gate any recommendation to flip the default to `true`
- If cost optimization is needed, a future ADR can split `INGEST_LLM_PROVIDER` from `LLM_PROVIDER` to allow a cheaper model (e.g., Haiku) for enrichment while using a stronger model (e.g., Sonnet) for chat
- The `enrichment_version` string is opaque to the pipeline — future structured versioning (e.g., `v1.0.0`) is backward-compatible

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **Opt-in enrichment, reuse `LLM_PROVIDER`** (selected) | Zero impact on existing deployments, no new abstraction, MTC-02 safe via version tuple | LLM cost per chunk, non-deterministic vectors | **Selected** |
| Always-on enrichment (no flag) | Simpler config surface | Breaks existing deployments, forces cost on all users, can't disable for debugging | Rejected — violates "zero impact" constraint and makes A/B comparison impossible |
| Dedicated `INGEST_LLM_PROVIDER` (separate from `LLM_PROVIDER`) | Enables Haiku-for-ingest + Sonnet-for-chat split | New provider knob, new factory branch, more surface area | Deferred — premature; add when cost data justifies it |
| Graph RAG (entity linking across docs) | Cross-document reasoning, richer entity graph | Requires graph DB or Qdrant payload graph traversal, significantly more complex pipeline, out of scope for current milestones | Rejected — wrong complexity/value trade-off at this stage |
| Semantic chunking via LLM (replace fixed chunker) | Chunk boundaries align with semantic units | Replaces the entire chunker, breaks MTC-02 (chunk boundaries change per re-run), very high token cost | Rejected — MTC-02 violation and operational risk outweigh the benefit |
| Replace `text` in payload with cleaned enriched text | Simpler payload, no dual-field complexity | Destroys citation display (MTC-04), raw text unrecoverable after ingest | Hard rejected — direct MTC-04 violation |

## References

- [BRD-01 §3.7](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — Hard Rules: MTC-01, MTC-02, MTC-04, MTC-10
- [BRD-01 §7.2 BRD.01.3206](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — AI/ML ADR topic
- `apps/api/src/config.py` — `INGEST_ENRICH`, `INGEST_ENRICH_VERSION`, `INGEST_ENRICH_CONCURRENCY`, `INGEST_ENRICH_MAX_TOKENS`
- `apps/api/src/ingestion/chunker.py` — `Chunk` extended with 6 enrichment fields, `embed_text()`, `with_enrichment()`
- `apps/api/src/ingestion/enrichment.py` — `enrich_chunks()`, `@observe(name="ingest.enrich")`, `asyncio.Semaphore` concurrency guard
- `apps/api/src/ingestion/pipeline.py` — enrichment spliced between dedupe and embed; embed call uses `c.embed_text()` instead of `c.text`
- `apps/api/tests/test_enrichment.py` — 14 tests covering enrichment, fallback, idempotency, and concurrency
- `.env.example` — documents the four new flags
- ADR-0006 — multi-provider LLM abstraction (the factory reused here)
- ADR-0008 — embedding model lock-in (MTC-01 contract upheld by this ADR)
- ADR-0003 — hybrid search pipeline (downstream consumer of the embedded vectors)
