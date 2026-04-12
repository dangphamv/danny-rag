# 0002. Qdrant over pgvector for the vector store

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3202 (Data Architecture)

## Context

The RAG pipeline needs a vector store. Constraints from BRD-01:

- Hybrid search is mandatory (MTC-03) — dense + BM25 + RRF must work first-class
- Idempotent upsert with content-hash dedupe (MTC-02)
- One collection per embedding model (MTC-01)
- Free-tier or near-free at MVP scale (BRD §13.1: <$30/mo total infra)
- Portable across hosting providers (no Railway lock-in for the vector layer)

The two realistic candidates were:

1. **Qdrant** — purpose-built vector DB, native sparse vector support, free 1 GB managed cluster
2. **pgvector** — Postgres extension; would let us share the existing Langfuse Postgres instance

## Decision

Use **Qdrant Cloud** (free tier) in production, **Qdrant in Docker** locally. Postgres stays for Langfuse + LangGraph checkpointer (separate role — see ADR-0010).

## Rationale

- **Hybrid search story**: Qdrant has native sparse vectors and a clean async client. pgvector requires separate BM25 implementation glued onto SQL queries — strictly more work for the same outcome.
- **Learning goal**: a dedicated vector DB has semantics worth understanding (HNSW indexing, payload filters, collection sharding). pgvector hides those behind SQL.
- **Decoupling from Postgres**: keeping the vector store off the relational instance pre-empts the noisy-neighbor risk that ADR-0010 already accepts for Langfuse + checkpointer. No reason to compound it with a third tenant.
- **Vendor portability**: Qdrant runs identically in Docker locally and Qdrant Cloud in prod. Same client, same API, idempotent ingestion makes the bootstrap a single command.
- **Free tier**: 1 GB cluster fits ~500k chunks at 1536d, well past MVP needs.

## Consequences

### Positive
- Hybrid search is one async function call, not a SQL query patched together
- The vector store is operationally independent — can swap to self-hosted Qdrant on a VPS without touching anything else
- Idempotent ingestion (MTC-02) is trivial: `client.upsert` with deterministic UUIDv5 IDs

### Negative
- **Two database systems** to operate (Qdrant + Postgres) instead of one
- **Network hop** adds ~5-15 ms per query vs in-process pgvector
- **No SQL access** to the corpus — debugging requires `curl localhost:6333/collections/...` or the `/qdrant-status` slash command

### Neutral / Follow-ups
- BM25 lives in-process via `rank-bm25` for now (ADR-0003); if corpus growth makes that untenable, switch to Qdrant native sparse vectors — that's a follow-up ADR, not this one
- The `/qdrant-status` slash command provides quick collection inspection

## Alternatives Considered

| Option | Function | Est. Monthly Cost | Selection Rationale |
|---|---|---|---|
| **Qdrant Cloud (free)** + Docker locally | Dedicated vector DB | $0–5 | **Selected** — hybrid-friendly, portable, free tier sufficient |
| pgvector on shared Postgres | Vectors inside Postgres | ~$0 (reuses Postgres) | Rejected — weak hybrid story; pulls a third tenant onto the noisy-neighbor instance |
| Weaviate Cloud | Managed vector DB | ~$25+ | Rejected — cost; less idiomatic Python client; no compelling differentiator |
| Pinecone | Managed vector DB | ~$70+ | Rejected — closed source; vendor lock; cost overruns the BRD budget cap |
| Chroma | Lightweight, embedded | $0 | Rejected — fewer production deployments; weaker hybrid support; learning goal favors Qdrant's broader ecosystem |

## References

- [BRD-01 §3.6](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — Technology Stack Prerequisites
- [BRD-01 §7.2 BRD.01.3202](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — Data Architecture topic
- [Qdrant docs](https://qdrant.tech/documentation/)
- ADR-0003 — hybrid search rationale
- ADR-0008 — embedding dimension lock-in
- ADR-0010 — shared Postgres trade-off
