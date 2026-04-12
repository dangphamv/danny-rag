# danny_rag — Project Instructions for Claude

## Stack
- **Backend**: FastAPI (Python 3.12), LangGraph, Qdrant, Langfuse self-hosted, DeepEval. Package manager: `uv`.
- **Frontend**: Next.js 15 App Router, Tailwind, shadcn, Vercel AI SDK `useChat`. Package manager: `pnpm`.
- **Vector store**: Qdrant (Docker locally, Qdrant Cloud in prod).
- **Relational DB**: Single Postgres shared by Langfuse and LangGraph checkpointer.
- **LLM providers**: Anthropic Claude (primary), OpenAI, Ollama (local). Switched via `LLM_PROVIDER` env.
- **Embeddings**: `text-embedding-3-small` (1536d, **locked**) primary. `nomic-embed-text` (768d) for local experiments only.
- **Hosts**: Railway (api + Langfuse), Vercel (web), Qdrant Cloud.

## Monorepo Layout
```
danny_rag/
├── apps/
│   ├── api/        # FastAPI backend (uv-managed)
│   └── web/        # Next.js 15 frontend (pnpm)
├── packages/
│   └── shared-types/   # zod ↔ pydantic schemas (created when needed)
├── docs/
│   ├── 01_BRD/     # Business Requirements (BRD-01 lives here)
│   └── adr/        # Architecture Decision Records (written retroactively per plan §10)
├── docker-compose.yml
├── plan.md         # canonical build plan — read first
└── .env.example
```

## Commands
- `docker compose up -d` — start Qdrant + Postgres + Langfuse locally
- `cd apps/api && uv run uvicorn src.main:app --reload` — run backend on `:8000`
- `cd apps/api && uv run pytest` — backend tests
- `cd apps/api && uv run ruff check src/` — lint
- `cd apps/api && uv run mypy src/` — type-check (strict)
- `cd apps/api && uv run deepeval test run evals/` — eval suite
- `cd apps/web && pnpm dev` — frontend on `:3000`
- `cd apps/web && pnpm build && pnpm tsc --noEmit` — web build + type-check

## Hard Rules (from BRD-01 §3.7 — non-negotiable)
1. **ADR required** for any dependency add or architectural change. Write the ADR before merging.
2. **All retrieval changes must ship with a DeepEval regression run.** No exceptions.
3. **One Qdrant collection per embedding model.** Switching `EMBED_PROVIDER` switches collection — never mix dimensions.
4. **Idempotent ingestion**: `doc_id + chunk_index` is the point ID; re-ingestion of identical content MUST produce zero new points (content-hash sha256 dedupe).
5. **Hybrid search is the default.** Dense + BM25 + RRF (k=60), then cross-encoder rerank top-50 → top-5. No single-path dense.
6. **Grounding system prompt is binding** — verbatim from BRD-01 §3.7 MTC-04. Faithfulness + Hallucination DeepEval metrics are blocking CI gates from Phase 7b.
7. **No `*` CORS.** Explicit origin allowlist only.
8. **API key auth** on `/chat` and `/ingest`. `/health` is the only public route.
9. **Token cap**: hard `max_tokens=1024` ceiling in the provider layer.
10. **Upload guards**: 25 MB cap, MIME allowlist, 60s timeout, 2-job concurrency semaphore.

## Coding Conventions
- Backend: ruff + mypy --strict. No `Any` outside boundaries.
- Frontend: ESLint + `tsc --noEmit`. No `any`.
- No comments unless the WHY is non-obvious.
- No backwards-compat shims for removed code.
- Validate only at system boundaries (HTTP input, file upload, env loading).

## Observability
- Wrap the LangGraph with `langfuse.callback.CallbackHandler`.
- Tag every trace with `env`, `user_id`, `session_id`, `model`.
- Thumbs up/down from UI posts back as Langfuse scores.

## Source-of-Truth Documents
- `plan.md` — canonical build plan (15 milestones).
- `docs/01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md` — Platform BRD.
- `docs/01_BRD/BRD-00_TRACEABILITY_MATRIX.md` — BRD index.

If those documents conflict with anything in this file, **the BRD wins** and this file should be updated.

## Project tooling (`.claude/` and `.mcp.json`)

This project ships its own subagents, slash commands, and MCP servers. See `.claude/README.md` for the full reference.

**Subagents** (in `.claude/agents/`):
- `rag-evaluator` — runs DeepEval, gates retrieval merges
- `adr-writer` — drafts MADR-format ADRs
- `ingestion-debugger` — traces failing docs through the pipeline
- `retrieval-tuner` — tunes hybrid params, runs ablations
- `langgraph-architect` — designs graph topology and state (opus)
- `security-auditor` — verifies the 11 MTCs from BRD-01 §3.7 are enforced

**Slash commands** (in `.claude/commands/`):
- `/eval [filter]` — DeepEval suite + verdict
- `/ingest-test <path>` — idempotency-checked ingestion
- `/trace [session]` — Langfuse trace inspection via postgres MCP
- `/adr <decision>` — draft an ADR
- `/milestone <N>` — verify milestone N exit criteria from plan §Phase 11
- `/qdrant-status` — collection + dimension sanity vs MTC-01/MTC-11

**MCP servers** (in `.mcp.json`):
- `context7` — live, version-specific docs for every library in the stack ("use context7" in any prompt)
- `postgres` — read-only access to local Langfuse Postgres
- `playwright` — browser automation for end-to-end UI tests

**Auto-delegation rules**: Claude routes work to the right subagent based on `description` matching. You can also call one explicitly with `@agent-name`. For UI changes, the dev server must be started and the feature exercised in Playwright before reporting "done".
