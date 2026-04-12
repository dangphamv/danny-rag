# 0003. Hybrid search (BM25 + dense + RRF) is the only retrieval path

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3206 (AI/ML), MTC-03

## Context

Pure dense retrieval is the easy default for an RAG project — embed the query, query Qdrant, return top-k. It works well for paraphrase-heavy queries (semantic similarity is what dense embeddings are designed for) and falls over on:

- Acronyms and identifiers (`MTC-09`, `text-embedding-3-small`)
- Exact-match keywords the embedder didn't see in training
- Numeric values
- Code snippets

Pure sparse retrieval (BM25) catches all those but falls over on the inverse: paraphrase, synonymy, and any query where the user uses different words than the corpus.

The BRD's learning hypothesis (§2.2) is that combining the two via Reciprocal Rank Fusion materially improves grounding quality, and that the improvement is measurable.

## Decision

All retrieval goes through `src/retrieval/hybrid.py:hybrid_search()`. It:

1. Fans out **dense** (Qdrant cosine similarity) and **sparse** (BM25 over the same chunk set) in parallel via `asyncio.gather`
2. Fuses the two ranked lists with **Reciprocal Rank Fusion at k=60**
3. Returns the fused top-N

Single-path dense retrieval is forbidden as the platform default per **MTC-03**. Code-review enforcement: the `security-auditor` subagent's checklist includes "MTC-03: hybrid_search exists and calls both dense + sparse + fuses".

BM25 lives in-process in `src/retrieval/sparse.py:BM25Index`, lazily built from Qdrant's full chunk set on first query and invalidated on every successful upsert (`pipeline.py` calls `invalidate_bm25_cache()`).

## Rationale

- **Industry consensus** as of 2026: hybrid > either path alone for retrieval quality, even before reranking. The Cormack/Clarke/Buettcher RRF paper plus a decade of follow-on work all converge on this.
- **k=60 is the canonical RRF constant** from the original paper. There's no compelling reason to tune it on a learning project; the value is robust across corpus sizes.
- **In-process BM25** is the simplest correct implementation. `rank-bm25` is well-known, ~200 lines of pure Python, no extra services.
- **Single retrieval path** simplifies the mental model: there's exactly one way to retrieve, and it's correct by default. No "fast path" / "slow path" branching.
- **Eval safety net**: the rerank ablation in `evals/test_rerank.py` provides empirical evidence the hybrid path stays good. If hybrid ever underperforms dense-only, the test catches it.

## Consequences

### Positive
- One function (`hybrid_search`) is the only retrieval entry point — fewer code paths to maintain
- Both retrieval styles get exercised every query, surfacing failures faster
- Mirrors how production RAG systems actually work — direct learning value

### Negative
- **Two retrieval systems** to maintain instead of one
- **BM25 index lifecycle**: must be invalidated after every upsert; bug in invalidation = stale results. Handled in `ingestion/pipeline.py` but it's an extra moving part
- **Adds ~30-80 ms latency** vs single-path dense (one extra in-process BM25 scan)
- **In-memory BM25 doesn't scale past ~100k chunks** comfortably — when that becomes a concern, switch to Qdrant native sparse vectors (future ADR)

### Neutral / Follow-ups
- The next step in the pipeline is reranking — see ADR-0004
- BM25 index rebuild is currently O(N) over the whole collection on first query after invalidation. For a 1k-chunk corpus that's ~50 ms; for 100k chunks it'd be ~5 s. Acceptable for hobby scale; revisit when metrics show it's a bottleneck.

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **Hybrid (BM25 + dense + RRF k=60)** | Best retrieval quality, mirrors production stacks | 2 systems, BM25 lifecycle | **Selected** — matches BRD §2.2 hypothesis |
| Dense only | Simplest, single path | Fails on keyword/identifier queries | Rejected — defeats the BRD hypothesis; would need a fallback path anyway |
| BM25 only | Cheap, no embeddings to run | Fails on paraphrase queries | Rejected — paraphrase is the primary RAG use case |
| Qdrant native sparse vectors | Single backend, no in-process BM25 | Schema change to existing collection; less mature client API | Rejected for v1 — defer until corpus growth makes in-process BM25 untenable |
| Weighted linear fusion (αD + (1-α)S) | Tunable | Per-corpus α tuning required; α drifts over time | Rejected — RRF is parameter-free at the fusion layer |
| Rank fusion via learned model | Optimal in theory | Requires training data; overkill for hobby project | Rejected — way too much machinery for the marginal lift |

## References

- [BRD-01 §3.7 MTC-03](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — hybrid search is mandatory
- [BRD-01 §7.2 BRD.01.3206](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — AI/ML topic
- [Cormack, Clarke, Buettcher — Reciprocal Rank Fusion (2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- `apps/api/src/retrieval/hybrid.py` — implementation
- `apps/api/src/retrieval/sparse.py` — BM25 lifecycle
- `apps/api/tests/test_rrf.py` — RRF unit tests
- ADR-0004 — cross-encoder reranking on top of fusion output
