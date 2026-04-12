# 0004. Cross-encoder reranking with BAAI/bge-reranker-base

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3206 (AI/ML)

## Context

Hybrid retrieval (ADR-0003) surfaces a top-50 candidate set. The LLM context budget needs top-5. Three things are true at once:

1. Bi-encoders (the dense retriever) score (query) and (doc) independently — fast but lossy
2. Cross-encoders score (query, doc) **pairs** — much more accurate, much slower
3. Production RAG stacks consistently use cross-encoder reranking on the post-fusion candidate set for the precision/latency trade-off

The plan (§Milestone 6) explicitly requires this and sets a verification gate: the reranker must show ≥10% NDCG@5 lift over fusion-only, otherwise its latency cost is unjustified and we fall back to a smaller model or skip it for short queries.

## Decision

Use **`BAAI/bge-reranker-base`** via the `sentence-transformers` `CrossEncoder` API. Run it on the post-RRF top-50 to produce the final top-5. Wrap the synchronous `model.predict` call in `asyncio.to_thread` so the event loop stays free for SSE streaming.

The reranker is loaded as a singleton via `@lru_cache` on `get_reranker()` in `src/retrieval/rerank.py` — model loading is ~500 MB on disk and ~2 s on cold start.

The mandatory ablation gate (`evals/test_rerank.py::test_rerank_lift_meets_minimum`) is the canary: if rerank stops earning its keep, the test fails and we drop it.

## Rationale

- **bge-reranker-base** is the strongest open-weights cross-encoder in the BAAI BGE family at the right size. Larger variants exist (`bge-reranker-v2-m3`, `bge-reranker-large`) but they push past the 3 s p95 latency budget on Railway hobby tier.
- **Local execution** = no per-query API cost, no extra vendor relationship. We pay once in disk space (~500 MB) and once in cold-start time, then it's free.
- **`sentence-transformers` CrossEncoder API** is well-known, stable, and integrates cleanly with the rest of the Python stack.
- **Singleton via `@lru_cache`** because each instance is expensive to construct. The `lru_cache` ensures one instance per process; `asyncio.to_thread` makes it safe to call concurrently.
- **`asyncio.to_thread`** is the right primitive for CPU-bound work in an async server. Avoids blocking the event loop and keeps SSE streams responsive.

## Consequences

### Positive
- Final retrieval quality is meaningfully higher than fusion-only (verified by `test_rerank.py`)
- Open-weights model = no vendor lock-in, no per-query cost
- The ablation test forces continued justification — if the reranker ever stops helping, we'll know

### Negative
- **+200-400 ms latency** per query (depends on chunk lengths and CPU)
- **~500 MB model download** on first request after a fresh deploy
- **Cold start**: ~2-3 s the very first time `get_reranker()` is called per process
- **CPU-bound** — won't benefit from multi-instance scaling unless each instance has its own copy

### Neutral / Follow-ups
- If p95 latency exceeds the 3 s budget on Railway hobby tier (BRD §2.3), the fallback ladder is documented in plan §Milestone 6:
  1. Switch to `bge-reranker-v2-m3` (smaller, faster, slightly less accurate)
  2. Add a query-level cache (LRU on `(query, top-50 IDs)`)
  3. Skip rerank for queries < N tokens
- The ablation test threshold is `+0.05` precision lift in Phase 7a (small dataset); tighten to ≥10% NDCG@5 in Phase 7b once dataset reaches ~100 cases
- Cohere's hosted Rerank API was considered as a managed alternative but rejected — see table below

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **bge-reranker-base** (sentence-transformers) | Open weights, free, strong quality | ~500 MB on disk, +200-400 ms latency | **Selected** — best fit for the constraints |
| bge-reranker-v2-m3 | Smaller, faster | Lower accuracy | Kept as documented fallback if v1 model exceeds latency budget |
| bge-reranker-large | Highest quality | Pushes past 3 s p95 budget | Rejected — latency too high for hobby tier |
| Cohere Rerank API | Best quality, managed | Closed source, $1/1k requests, vendor relationship | Rejected — adds vendor lock + cost; defeats the open-source learning goal |
| Skip reranking entirely | Simplest, lowest latency | Violates BRD §2.2 hypothesis | Rejected — the whole point is to measure whether rerank helps |
| LLM-as-reranker | High quality | 10× the latency, 100× the cost | Rejected — wildly disproportionate to the marginal lift |

## References

- [BRD-01 §7.2 BRD.01.3206](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — AI/ML topic, ablation requirement
- [BRD-01 §2.3](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — p95 latency target (<3 s)
- `plan.md` §Milestone 6 — explicit ablation requirement
- `apps/api/src/retrieval/rerank.py` — implementation
- `apps/api/evals/test_rerank.py` — ablation test
- ADR-0003 — hybrid retrieval that feeds the reranker
- ADR-0007 — DeepEval suite that runs the ablation
