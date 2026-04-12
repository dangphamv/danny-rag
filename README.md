# danny_rag

A production-shaped RAG knowledge chatbot — built end-to-end as a learning project.

**Stack** (full reasoning in [BRD-01](docs/01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md)):

- **Backend**: FastAPI + LangGraph + Qdrant (hybrid BM25+dense+RRF) + cross-encoder rerank + DeepEval
- **Frontend**: Next.js 15 (App Router) + Vercel AI SDK `useChat`
- **LLM providers**: Anthropic Claude / OpenAI / Ollama (pluggable via env)
- **Embeddings**: `text-embedding-3-small` (1536d, locked)
- **Observability**: Langfuse v3 self-hosted
- **Hosts**: Railway (api + Langfuse), Vercel (web), Qdrant Cloud

## Repository Layout

```
danny_rag/
├── apps/
│   ├── api/        # FastAPI backend (uv-managed Python 3.12)
│   └── web/        # Next.js 15 frontend (pnpm) — created in milestone 9
├── docs/
│   ├── 01_BRD/     # Business requirements (BRD-01 lives here)
│   └── adr/        # 10 Architecture Decision Records (M14)
├── .claude/        # project subagents + slash commands (see .claude/README.md)
├── .mcp.json       # project-scoped MCP servers (context7, postgres, playwright)
├── docker-compose.yml
├── plan.md         # canonical 15-milestone build plan
└── CLAUDE.md       # project rules + tooling reference
```

## Prerequisites

```bash
# Runtimes
brew install node@20 python@3.12 pnpm
brew install --cask docker         # Docker Desktop
brew install ollama                # local LLM runtime (optional, for offline)
brew install uv                    # fast Python package manager
brew install gh                    # GitHub CLI

# Pull local models once Ollama is running (optional)
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

Verify: `node -v && python3 --version && docker --version && uv --version`.

## Quick Start (Milestone 1 + 2)

### 1. Bring up the data plane

```bash
cp .env.example .env
# edit .env — add ANTHROPIC_API_KEY and OPENAI_API_KEY
docker compose up -d
```

This brings up Qdrant (`:6333`), Langfuse (`:3001`), Postgres (`:5432`), ClickHouse, Redis, and MinIO. Wait ~30s for Langfuse migrations to finish on first boot.

Verify:

```bash
curl -sf http://localhost:6333/readyz       # Qdrant
curl -sfI http://localhost:3001 | head -1   # Langfuse web (expect HTTP/1.1 200)
```

Open <http://localhost:3001> and log in with `dev@local` / `dev-password-change-me`. The `danny-rag` project is auto-created.

### 2. Run the API

```bash
cd apps/api
uv sync                                          # install deps from pyproject.toml
uv run uvicorn src.main:app --reload --port 8000
```

Verify:

```bash
curl -s http://localhost:8000/health | jq
# {"status": "ok", "version": "0.1.0", "env": "local"}
```

### 3. Ingest a document, then run the chat UI

```bash
# in apps/api
cd apps/api
uv run python -m src.ingestion.cli ../../data/sample.txt

# in apps/web (separate terminal)
cd apps/web
cp .env.local.example .env.local      # API_URL + API_KEY (server-side only)
pnpm install
pnpm dev                              # http://localhost:3000
```

Open <http://localhost:3000>, ask a question, watch tokens stream and the sources panel populate.

### 4. Deploy to production

See [`docs/DEPLOY.md`](docs/DEPLOY.md) for the full Railway + Vercel + Qdrant Cloud + Langfuse runbook (~90 minutes for first deploy, auto-deploy on push thereafter).

### 5. Architectural decisions

10 ADRs in [`docs/adr/`](docs/adr/) document the trade-offs that shaped this stack — Qdrant vs pgvector, hybrid retrieval, the LLM Protocol leakage points, the shared-Postgres mitigation triggers, and so on. Start with [ADR-0001](docs/adr/0001-record-architecture-decisions.md) for the format and meta-decision.

## Working with this repo in Claude Code

This project ships its own subagents, slash commands, and MCP servers under `.claude/` and `.mcp.json`. Restart Claude Code once after first clone — you'll be prompted to approve the project MCPs.

See [.claude/README.md](.claude/README.md) for the full reference and workflow recipes.

## Hard Rules

The 11 mandatory technology conditions (MTC-01 to MTC-11) live in [BRD-01 §3.7](docs/01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md#37-mandatory-technology-conditions-non-negotiable-platform-constraints) and are non-negotiable. The `security-auditor` subagent verifies them in code before every deploy.

## Plan

[`plan.md`](plan.md) is the canonical 15-milestone build plan. Read it first.

## License

Personal learning project. Not for production use as-is.
