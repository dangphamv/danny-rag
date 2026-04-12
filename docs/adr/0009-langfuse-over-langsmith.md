# 0009. Langfuse self-hosted over LangSmith

- **Status**: Accepted (with documentation gap noted)
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3205 (Observability)

## Context

LLM observability is the safety net for everything in this project. Traces of retrieve / rerank / generate calls are how you debug:

- A retrieval regression that the eval suite caught (which chunks were returned?)
- A latency spike (which stage was slow?)
- A hallucination report from a user (what context did the model see?)
- Token-cost surprises (which prompt was expensive?)

Two main contenders as of 2026:

1. **LangSmith** — LangChain's hosted observability product. Tightly integrated with LangChain Runnables. Hosted-only.
2. **Langfuse** — open-source alternative. Self-hostable. Multi-framework.

The BRD §3.7 BRD.01.3205 makes "self-hosted, owns-your-data" a hard constraint.

## Decision

**Self-host Langfuse.** Same instance runs locally (via `docker-compose.yml`) and in production (Railway). Same `LANGFUSE_HOST` URL pattern, just different domains.

The Langfuse client is initialized in `src/observability/langfuse.py` and flushed in the FastAPI lifespan.

## Rationale

- **Data sovereignty**: trace data is sometimes sensitive (user questions can contain PII, system prompts are IP). Self-hosting means we own the data, no DPA negotiations, no jurisdictional surprises
- **Cost**: LangSmith bills per-trace at scale; self-hosted Langfuse is bounded by compute cost regardless of trace volume. For a learning project this is the difference between $0 and "watch the meter"
- **Multi-framework**: Langfuse works equally well with LangChain, raw OpenAI/Anthropic SDKs, or our own Protocol-wrapped providers. LangSmith is biased toward LangChain Runnables
- **Open source**: bug reports turn into upstream fixes, not support tickets. The codebase is auditable
- **Single deploy story**: official Railway template exists, so production parity is one-click

## Consequences

### Positive
- Trace data lives in our Postgres + ClickHouse, never leaves Railway
- Same observability stack locally and in prod — no "works in dev, missing in prod" surprises
- No per-trace billing concerns
- Spans can be added with `@observe()` decorators to any function, not just LangChain Runnables

### Negative — the BRD documentation gap

**The BRD-01 §7.2 BRD.01.3205 was written assuming Langfuse v2's single-binary architecture.** That was correct at the time of writing but **Langfuse v2 is deprecated as of 2026**. Langfuse v3, the current version, requires:

- Postgres (metadata)
- **ClickHouse** (actual trace storage — this is the big change)
- **Redis** (queue + cache)
- **MinIO/S3** (blob storage for large prompts/outputs)
- Two service containers: `langfuse-web` + `langfuse-worker`

`docker-compose.yml` reflects v3 reality with an explanatory comment. The BRD's "single-binary" recommendation in §7.2 BRD.01.3205 is now stale. **The BRD should be bumped to v1.2 to update §3.6 (add ClickHouse/Redis/MinIO to the stack table) and §7.2 BRD.01.3205 (the deploy story is more involved than "single binary on Railway").**

This ADR is the audit trail for the deviation. The next BRD revision should reference it.

### Negative — operational
- **More moving parts** than v2 (6 services vs 1) → higher local Docker resource cost
- **Self-hosting cost** in compute time = ~6 services running 24/7
- **Cold start** of the full stack on `docker compose up` takes ~60 s (mostly ClickHouse + Postgres migrations)
- **Initial setup** requires populating LANGFUSE_INIT_* env vars to auto-create the org/project/user

### Neutral / Follow-ups
- Langfuse callback wiring into the LangGraph execution: **wired**. `src/observability/langfuse.py:get_callback_handler()` returns a `langfuse.langchain.CallbackHandler` bound to the global client; `src/routes/chat.py:_build_graph_config()` constructs `{"callbacks": [handler], "metadata": {"langfuse_session_id": ..., "langfuse_user_id": ..., "langfuse_tags": [...]}}` and passes it to `graph.astream()`. Every node fires `on_chain_start`/`on_chain_end` events that the handler converts to spans automatically. Each LLM call inside a node gets its own child span via `@observe()` on the provider methods (`anthropic.generate`, `openai.astream`, `ollama.generate`, etc.)
- The `/trace` slash command uses the `postgres` MCP to query Langfuse Postgres directly for fast trace inspection
- Production cost: Langfuse on Railway hobby tier shares the existing Postgres and adds ClickHouse + Redis + MinIO. Estimated marginal cost: $5-10/mo

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **Langfuse self-hosted (v3)** | OSS, owns data, multi-framework, Railway template | 6 services to operate, BRD doc drift from v2 assumption | **Selected** — fits BRD constraints despite operational complexity |
| LangSmith hosted | Best-in-class LangChain integration, polished UI, zero ops | Hosted-only, per-trace billing, vendor lock, data residency concerns | Rejected — fails the "owns-your-data" BRD constraint |
| OpenTelemetry + Tempo + Grafana DIY | Vendor-neutral, industry standard | Not LLM-specific; need to glue everything; no built-in LLM concepts (prompts, outputs, scores) | Rejected — too much glue for the LLM-specific use case |
| Phoenix (Arize) | Open source, LLM-native | Smaller ecosystem than Langfuse, less Railway integration | Rejected — Langfuse is the broader fit |
| Helicone | Cheap, OpenAI-shaped proxy | Hosted-only, only catches OpenAI traffic | Rejected — multi-provider requirement |
| No observability | Zero ops | The whole BRD safety net falls apart | Rejected — observability is non-negotiable per BRD |

## References

- [BRD-01 §3.7 MTC](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — observability requirement
- [BRD-01 §7.2 BRD.01.3205](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — Observability topic (currently stale on the v2/v3 detail — see "Documentation gap" above)
- [Langfuse v3 architecture migration discussion](https://github.com/orgs/langfuse/discussions/1902)
- [Langfuse self-hosting docs](https://langfuse.com/self-hosting)
- `docker-compose.yml` — v3 stack with explanatory comment
- `apps/api/src/observability/langfuse.py` — client initialization
- ADR-0010 — shared Postgres for Langfuse + LangGraph checkpointer
