# Architecture Decision Records

Markdown ADRs in MADR format. See [ADR-0001](0001-record-architecture-decisions.md) for the meta-decision and the format.

## Index

| # | Title | BRD Topic | Status |
|---|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | meta | Accepted |
| [0002](0002-choose-qdrant-over-pgvector.md) | Qdrant over pgvector for the vector store | BRD.01.3202 | Accepted |
| [0003](0003-hybrid-search-bm25-plus-dense.md) | Hybrid search (BM25 + dense + RRF) is the only retrieval path | BRD.01.3206 / MTC-03 | Accepted |
| [0004](0004-cross-encoder-reranking.md) | Cross-encoder reranking with `BAAI/bge-reranker-base` | BRD.01.3206 | Accepted |
| [0005](0005-langgraph-for-orchestration.md) | LangGraph over plain LangChain chains for graph orchestration | BRD.01.3203 / 3207 | Accepted |
| [0006](0006-multi-provider-llm-abstraction.md) | Multi-provider LLM abstraction via a thin Protocol | BRD.01.3203 | Accepted |
| [0007](0007-deepeval-for-offline-evals.md) | DeepEval for offline retrieval and answer-quality evaluation | BRD.01.3206 / MTC-05 | Accepted |
| [0008](0008-embedding-model-and-dimension-lock-in.md) | Embedding model and dimension lock-in | BRD.01.3206 / MTC-01 / MTC-11 | Accepted |
| [0009](0009-langfuse-over-langsmith.md) | Langfuse self-hosted over LangSmith | BRD.01.3205 | Accepted (BRD doc gap noted) |
| [0010](0010-shared-postgres-for-langfuse-and-checkpointer.md) | Shared Postgres for Langfuse and the LangGraph checkpointer | BRD.01.3202 | Accepted (mitigation plan) |

## Authoring new ADRs

Use the `/adr <one-line decision summary>` slash command — it delegates to the `adr-writer` subagent in `.claude/agents/`. The subagent picks the next sequential number, maps the decision to a BRD.01.32xx topic, and drafts the standard sections.

## Outstanding decisions worth ADRs

These are architectural deviations made during implementation that have been *documented inside ADRs* but are not yet ADRs of their own. If they grow in scope they should each get one:

1. **Custom `useChat` hook instead of Vercel AI SDK** (M9) — currently noted in `apps/web/README.md` and ADR-0005's references. Promote to its own ADR if the AI SDK story changes.
2. **Server-side SSE proxy via Next.js route handler keeping API key off the browser** (M9) — currently noted in `apps/web/README.md`. Strong candidate for its own ADR.
3. **Self-grading loop with `MAX_REWRITES = 2` and `GROUNDING_THRESHOLD = 0.7`** (M10) — currently a tested constant; documented in ADR-0005's "Consequences". Promote if the threshold is ever changed.
4. **Tailwind v4 CSS-first config** (M9) — small enough to live in `apps/web/README.md`.
5. **BRD v1.2 update for Langfuse v3 stack** — flagged inside ADR-0009. Should be a BRD revision, not a new ADR.
