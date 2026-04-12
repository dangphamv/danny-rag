# RAG-Powered Knowledge Base Chatbot — Build & Learn Plan

## Context
Greenfield learning project in `/Users/dangpham/project/danny_rag` (currently empty). Goal: build a production-shaped RAG chatbot end-to-end to learn the modern RAG stack — hybrid retrieval, reranking, agentic orchestration, evaluation, and observability — while producing a real deployable artifact.

**Stack decisions (from Q&A):**
- Vector store: **Qdrant** (cloud for deploy, Docker for local)
- LLMs: **Anthropic Claude + OpenAI + Ollama (local)** — pluggable provider layer
- Backend host: **Railway**
- Observability: **Langfuse self-hosted**
- Frontend host: **Vercel**

**Why this design:** Each piece maps to a learning objective — Qdrant teaches vector DB internals; multi-provider LLM layer teaches abstraction; LangGraph teaches agentic state machines; DeepEval teaches retrieval metrics; Langfuse teaches tracing; ADRs teach decision hygiene.

---

## Phase 0 — Accounts to create

| Service | Why | URL |
|---|---|---|
| **GitHub** | Source control, Actions CI | github.com |
| **Anthropic Console** | Claude API key (`ANTHROPIC_API_KEY`) | console.anthropic.com |
| **OpenAI Platform** | GPT + `text-embedding-3-small` key | platform.openai.com |
| **Qdrant Cloud** | Managed vector DB (free 1GB cluster) | cloud.qdrant.io |
| **Vercel** | Next.js frontend hosting | vercel.com |
| **Railway** | FastAPI backend + Langfuse Postgres | railway.app |
| **Langfuse** | (optional hosted fallback) | langfuse.com |

Store every key in a password manager. Never commit `.env`.

---

## Phase 1 — Local tools to install

```bash
# Runtimes
brew install node@20 python@3.12 pnpm
brew install --cask docker          # Docker Desktop (for local Qdrant, Langfuse, Postgres)
brew install ollama                 # local LLM runtime
brew install uv                     # fast Python package manager (replaces pip/poetry)
brew install gh                     # GitHub CLI
brew install railway                # Railway CLI
pnpm add -g vercel                  # Vercel CLI

# Pull local models once Ollama is running
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

Verify: `node -v && python3 --version && docker --version && uv --version && ollama list`.

---

## Phase 2 — Claude Code setup for this project

### 2.1 MCP servers to add
Add to `~/.claude/mcp.json` (or via `claude mcp add`):
- **filesystem** — already in your global config; scope to `~/project/danny_rag`
- **github** — PRs, issues, code search (needs `GITHUB_TOKEN`)
- **fetch** — pull docs from Qdrant / LangGraph / Langfuse sites during coding
- **postgres** (optional) — query Langfuse's DB when debugging traces

Skip `apple-calendar` and `memory` — not relevant here.

### 2.2 Project-level `CLAUDE.md`
Create `/Users/dangpham/project/danny_rag/CLAUDE.md` with:
- Stack summary (so future sessions don't re-ask)
- Monorepo layout
- Commands (`pnpm dev`, `uv run uvicorn …`, `docker compose up`)
- Rule: "ADR required for any dependency add or architecture change"
- Rule: "All retrieval changes must ship with a DeepEval regression run"

### 2.3 Plugins / skills already installed that apply
- `/commit`, `/review-pr` — use after each milestone
- `/simplify` — run after each feature PR to catch over-engineering
- `/feature`, `/design` — for new modules
- `/security-check` — before deploy

### 2.4 Subagents worth defining
Create `.claude/agents/` in the repo with:
- **rag-evaluator** — runs DeepEval suite, summarizes deltas vs. baseline
- **adr-writer** — drafts new ADRs from a one-line decision prompt
- **ingestion-debugger** — given a failing doc, traces it through loader → chunker → embedder → Qdrant

---

## Phase 3 — Repo structure (monorepo via pnpm workspaces)

```
danny_rag/
├── CLAUDE.md
├── README.md
├── .env.example
├── docker-compose.yml           # Qdrant + Langfuse + Postgres locally
├── pnpm-workspace.yaml
├── docs/
│   └── adr/
│       ├── 0001-record-architecture-decisions.md
│       ├── 0002-choose-qdrant-over-pgvector.md
│       ├── 0003-hybrid-search-bm25-plus-dense.md
│       ├── 0004-cross-encoder-reranking.md
│       ├── 0005-langgraph-for-orchestration.md
│       ├── 0006-multi-provider-llm-abstraction.md
│       ├── 0007-deepeval-for-offline-evals.md
│       ├── 0008-embedding-model-and-dimension-lock-in.md
│       ├── 0009-langfuse-over-langsmith.md
│       └── 0010-shared-postgres-for-langfuse-and-checkpointer.md
├── apps/
│   ├── web/                     # Next.js 15 (App Router)
│   └── api/                     # FastAPI
├── packages/
│   └── shared-types/            # zod + pydantic schemas mirrored
└── .github/workflows/
    ├── api-ci.yml
    ├── web-ci.yml
    └── eval.yml                 # nightly DeepEval run
```

---

## Phase 4 — Backend (`apps/api`) setup

### 4.0 Security & limits (non-negotiable, wire in from day one)
- **Auth:** static `X-API-Key` header checked by a FastAPI dependency on `/chat` and `/ingest`. Key stored in Railway env, injected into Vercel as `NEXT_PUBLIC_`-free server-side env. `/health` stays public.
- **CORS:** explicit origin allowlist — the exact Vercel prod + preview URLs. No `*`.
- **Rate limit:** `slowapi` per-IP — `/chat` 20/min, `/ingest` 5/min. Raise after first week if too tight.
- **Token cap:** hardcoded `max_tokens` ceiling in the provider layer (e.g., 1024 output). Prompt rejection if input context exceeds provider-specific budget.
- **Ingestion DoS guards:** `UploadFile` size check (25 MB hard cap), MIME allowlist (`application/pdf`, `text/markdown`, `text/html`, `text/plain`), per-file ingestion timeout (60 s), semaphore bounding concurrent ingestion jobs to 2.
- **Budget alerts:** set spend alerts in Anthropic + OpenAI dashboards manually after first deploy. Not code, but a checklist item in Phase 9.

### 4.1 Bootstrap
```bash
cd apps/api
uv init --package
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings python-multipart
uv add qdrant-client langchain langchain-community langchain-anthropic langchain-openai langchain-ollama
uv add langgraph langgraph-checkpoint-postgres
uv add rank-bm25 sentence-transformers   # BM25 + cross-encoder reranker
uv add "unstructured[pdf,md]" beautifulsoup4 tiktoken
uv add langfuse slowapi
uv add --dev pytest pytest-asyncio ruff mypy deepeval
```

### 4.2 Module layout
```
apps/api/src/
├── main.py                  # FastAPI app, CORS, lifespan
├── config.py                # pydantic-settings, all env vars
├── llm/
│   ├── provider.py          # Protocol: generate(), stream(), embed()
│   ├── anthropic.py
│   ├── openai.py
│   └── ollama.py
├── ingestion/
│   ├── loaders.py           # PDF, MD, HTML, URL
│   ├── chunker.py           # recursive + semantic chunking
│   ├── pipeline.py          # load → chunk → embed → upsert
│   └── cli.py               # `uv run ingest ./data`
├── retrieval/
│   ├── dense.py             # Qdrant similarity
│   ├── sparse.py            # BM25 over same doc set
│   ├── hybrid.py            # RRF fusion
│   └── rerank.py            # cross-encoder (bge-reranker-base)
├── graph/
│   ├── state.py             # LangGraph TypedDict state
│   ├── nodes.py             # rewrite → retrieve → rerank → generate → grade
│   └── build.py             # StateGraph wiring + Langfuse callback
├── routes/
│   ├── chat.py              # POST /chat (SSE stream)
│   ├── ingest.py            # POST /ingest
│   └── health.py
└── observability/
    └── langfuse.py          # singleton client + decorators
```

### 4.3 Key implementation notes
- **Embedding model (locked):** `text-embedding-3-small` (1536d) is the primary. One Qdrant collection per embedding model; `EMBED_PROVIDER` switches collection, never mixes. Ollama `nomic-embed-text` (768d) gets its own collection for offline/local experiments. See ADR 0008.
- **Chunking (concrete defaults):** `RecursiveCharacterTextSplitter`, chunk_size=512 tokens, chunk_overlap=64, separators `["\n\n", "\n", ". ", " "]`. Semantic chunking (via `langchain_experimental.SemanticChunker`) runs as a Phase 7 ablation only — do not ship as default until DeepEval shows a win.
- **Chunk metadata schema:** `{doc_id, source_uri, title, page, section, chunk_index, content_hash, ingested_at, embedding_model}`. `doc_id + chunk_index` is the Qdrant point ID. `content_hash` (sha256 of raw text) drives idempotent upsert — re-ingesting the same doc must not create duplicates.
- **Hybrid search:** run dense + BM25 in parallel, fuse with Reciprocal Rank Fusion (`k=60`), then rerank top-50 to top-5 with `BAAI/bge-reranker-base`.
- **LangGraph:** nodes = `rewrite_query → retrieve → rerank → generate → self_grade`. `self_grade` loops back to `rewrite_query` once if grounding score < threshold.
- **System prompt contract (grounding discipline):** the generator node's system prompt states literally: *"Answer only from the provided context. Cite source chunks by `doc_id`. If the context is insufficient, reply `I don't have enough information to answer that` and stop. Do not use prior knowledge."* Tested by DeepEval Faithfulness + Hallucination metrics as **blocking CI gates**, not advisory.
- **Streaming:** FastAPI `StreamingResponse` with SSE, one token per event. LangGraph's `astream_events` feeds this. Source citations ship as a final SSE `data:` frame (not interleaved with tokens) so the UI can render the sources panel after the stream completes — validate wire format in milestone 8 before building milestone 9.
- **Langfuse:** wrap the graph with `CallbackHandler` from `langfuse.callback`. Every retrieval, rerank, and LLM call shows up as a span.

### 4.4 Env vars (`.env.example`)
```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
LLM_PROVIDER=anthropic          # anthropic|openai|ollama
EMBED_PROVIDER=openai           # openai|ollama
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3001
POSTGRES_URL=                   # for LangGraph checkpointer
```

---

## Phase 5 — Frontend (`apps/web`) setup

```bash
cd apps/web
pnpm create next-app@latest . --ts --tailwind --app --eslint --src-dir --import-alias "@/*"
pnpm add ai @ai-sdk/react zod
pnpm add lucide-react class-variance-authority clsx tailwind-merge
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button input textarea card scroll-area
```

**Streaming UI**: use Vercel AI SDK's `useChat` hook pointed at the FastAPI `/chat` SSE endpoint. Render source citations from each assistant message's `data` field (retrieved chunks with doc_id + snippet). Add a sidebar showing "sources used" for the last answer — a visible proof of the RAG loop.

Pages:
- `/` — chat UI
- `/ingest` — drag-drop file upload → `POST /ingest`
- `/traces` — iframe to Langfuse (or just a link)

---

## Phase 6 — Local dev (`docker-compose.yml`)
Services: `qdrant`, `postgres` (for Langfuse + LangGraph checkpointer), `langfuse-server`, `langfuse-worker`. One command `docker compose up -d` brings up the whole data plane.

---

## Phase 7 — Evaluation (DeepEval)

```
apps/api/evals/
├── dataset.jsonl           # grows over two sub-phases (see below)
├── test_retrieval.py       # ContextualRecall, ContextualPrecision, NDCG@5
├── test_rerank.py          # NDCG@5 pre-rerank vs post-rerank (isolates the reranker)
├── test_answer.py          # AnswerRelevancy, Faithfulness (blocking), Hallucination (blocking)
└── baselines/              # JSON snapshots per commit
```

### Phase 7a — Seed baseline (runs during milestone 11)
- 30–50 Q/A pairs seeded from the first ingested docs. Enough to surface obvious breakage, not enough to trust tight thresholds.
- Run locally: `uv run deepeval test run apps/api/evals/`.
- Store first baseline snapshot in `baselines/`.
- CI runs the suite but **does not block** merges yet — reports only.

### Phase 7b — Enable the CI gate (before Phase 9 deploy)
- Expand dataset to 100–200 Q/A pairs (mix of extractive, multi-hop, and out-of-scope "should refuse" cases).
- Out-of-scope cases are mandatory — they're how you test the system-prompt grounding contract from 4.3.
- Wire into GitHub Actions (`eval.yml`) as a nightly cron. Regression policy: retrieval precision drop >5% **OR** Faithfulness/Hallucination regression **at all** opens an issue automatically.
- Consider a statistical floor (2σ over the last 7 runs) instead of a fixed 5% — the small-sample variance on 30–50 pairs is the reason Phase 7a can't have a blocking gate.
- Reranker ablation (`test_rerank.py`) must show NDCG@5 improvement over fusion-only; otherwise the reranker's latency cost isn't justified and it should be dropped or swapped.

---

## Phase 8 — Observability (Langfuse self-hosted)
- Local: in `docker-compose.yml`.
- Prod: deploy Langfuse to Railway as a second service, reuse the same Postgres. Point `LANGFUSE_HOST` at `https://langfuse.<your>.railway.app`.
- Add `@observe()` decorators on `retrieve`, `rerank`, `generate`. Tag traces with `env`, `user_id`, `session_id`, `model`. Use Langfuse scores to track thumbs up/down from the UI.

---

## Phase 9 — Deployment
- **Frontend:** `vercel link` in `apps/web`, set `NEXT_PUBLIC_API_URL` env + server-side `API_KEY` (for the auth header, never exposed to the client), auto-deploy on main.
- **Backend:** `railway init` in `apps/api`, `railway up`. Point at Qdrant Cloud (not Railway add-on — keeps vector store portable). Expose `/chat` with CORS locked to exact Vercel prod + preview domains.
- **Langfuse:** deploy via Railway template — official one-click exists.
- **Qdrant bootstrap (local → prod):** ingestion is run-anywhere because upserts are content-hash idempotent (see 4.3). Prod bootstrap = point the ingest CLI at `QDRANT_URL=<cloud>` and re-run against the same source corpus. Do **not** try to snapshot local Docker Qdrant into Cloud — re-ingest is cleaner and exercises the pipeline.
- **Secrets:** only in Vercel/Railway dashboards. Never in repo. Includes `API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `QDRANT_API_KEY`, Langfuse keys, `POSTGRES_URL`.
- **Budget alerts (manual checklist):** set spend alerts on Anthropic + OpenAI consoles on the day of first deploy. Not code — still mandatory.
- **CI:** GitHub Actions — lint (ruff) + mypy (strict on `src/`) + pytest for api, `pnpm build` + `tsc --noEmit` for web, DeepEval nightly (blocking only after Phase 7b).

---

## Phase 10 — ADRs to write (in order, as you hit each decision)
1. Record architecture decisions (meta ADR — template)
2. Qdrant over pgvector — capture the hybrid search + learning-curve reasoning
3. Hybrid search (BM25 + dense + RRF) — why fusion beats either alone
4. Cross-encoder reranking — latency/quality trade-off + NDCG ablation requirement
5. LangGraph over plain LangChain chains — state + self-grading loop
6. Multi-provider LLM abstraction — the `Provider` protocol and where it leaks (streaming shapes, tool-call semantics, token counting differ per provider)
7. DeepEval for offline evals — why not "vibes-only" testing
8. **Embedding model & dimension lock-in** — why `text-embedding-3-small` is primary, why one-collection-per-embedder, what it would cost to switch later
9. **Langfuse over LangSmith** — self-hosted, OSS, owns-your-data, single-binary Railway deploy; LangSmith's hosted-only model and data-residency trade-off rejected
10. **Shared Postgres for Langfuse + LangGraph checkpointer** — accept the noisy-neighbor trade-off for learning-project cost; split if write contention appears

Use MADR template (`adr-tools` or just markdown). Each ADR: Context / Decision / Consequences / Alternatives considered.

---

## Phase 11 — Milestones (suggested order, each ~1 evening)

1. Repo scaffold + `docker-compose up` brings Qdrant + Langfuse online
2. FastAPI hello world + health check + Langfuse initialized
3. Ingestion pipeline: load a PDF → chunk → embed → upsert to Qdrant (CLI only)
4. Dense retrieval endpoint `/search?q=…` returning top-k chunks
5. Add BM25 + RRF fusion, compare results
6. Add cross-encoder reranker — measure p95 end-to-end latency (budget: <3s on Railway hobby tier) and NDCG@5 vs fusion-only. If the latency budget blows or NDCG doesn't improve, drop to `bge-reranker-v2-m3`, add a query-level cache, or skip reranking for short queries
7. LangGraph skeleton: rewrite → retrieve → generate (no loop yet)
8. Streaming `/chat` endpoint with SSE
9. Next.js chat UI with `useChat` wired to `/chat`
10. Self-grading loop in LangGraph (grounding check → rewrite once)
11. DeepEval dataset + first baseline run
12. File upload UI → `/ingest`
13. Deploy: Railway (api) + Vercel (web) + Langfuse
14. Write all ADRs retroactively while the reasoning is fresh
15. Run `/simplify` and `/review-pr` passes

---

## Critical files (will be created)
- `/Users/dangpham/project/danny_rag/CLAUDE.md`
- `/Users/dangpham/project/danny_rag/docker-compose.yml`
- `/Users/dangpham/project/danny_rag/apps/api/src/main.py`
- `/Users/dangpham/project/danny_rag/apps/api/src/graph/build.py` — the heart of the system
- `/Users/dangpham/project/danny_rag/apps/api/src/retrieval/hybrid.py`
- `/Users/dangpham/project/danny_rag/apps/web/src/app/page.tsx`
- `/Users/dangpham/project/danny_rag/docs/adr/*`

## Reused libraries (don't reinvent)
- `rank-bm25` — BM25 scoring
- `sentence-transformers` CrossEncoder — reranking (`BAAI/bge-reranker-base`)
- LangChain loaders — `unstructured` for PDF, `RecursiveCharacterTextSplitter` for chunking
- LangGraph `StateGraph` + `PostgresCheckpointer` — no custom state machine
- Vercel AI SDK `useChat` — no custom streaming client
- Langfuse `CallbackHandler` — no custom tracing

---

## Verification (end-to-end test)
1. `docker compose up -d` — Qdrant on 6333, Langfuse on 3001 reachable
2. `cd apps/api && uv run ingest ../../data/sample.pdf` — log shows N chunks upserted
3. `uv run uvicorn src.main:app --reload` — `curl localhost:8000/health` returns ok
4. `cd apps/web && pnpm dev` — open `localhost:3000`, ask a question from the PDF
5. Answer streams token-by-token; sources panel shows 3–5 chunks with doc_id
6. Open Langfuse at `localhost:3001` — see full trace: rewrite → retrieve (k=50) → rerank (k=5) → generate
7. `cd apps/api && uv run deepeval test run evals/` — all metrics above threshold
8. Deploy to Railway + Vercel, repeat steps 4–6 against prod URLs
9. Break something (e.g., drop reranker) → nightly eval flags regression → confirms the safety net works
