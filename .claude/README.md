# Project Claude Code Setup

Everything in this directory is project-scoped — it lives in version control so future sessions, future you, and any collaborator gets the same agents, commands, and MCP servers automatically.

## Layout

```
.claude/
├── README.md            # this file
├── agents/              # 6 subagents (delegated work, isolated context)
│   ├── rag-evaluator.md
│   ├── adr-writer.md
│   ├── ingestion-debugger.md
│   ├── retrieval-tuner.md
│   ├── langgraph-architect.md
│   └── security-auditor.md
└── commands/            # 6 slash commands (workflow shortcuts)
    ├── eval.md
    ├── ingest-test.md
    ├── trace.md
    ├── adr.md
    ├── milestone.md
    └── qdrant-status.md
```

Plus `.mcp.json` at the project root — three MCP servers wired in.

## MCP servers (`.mcp.json`)

| Server | Why | Command |
|---|---|---|
| **context7** | Pulls live, version-specific docs for Qdrant, LangGraph, FastAPI, Langfuse, DeepEval, Next.js, shadcn into the prompt. Add "use context7" to any question to auto-fetch. | `npx -y @upstash/context7-mcp` |
| **postgres** | Read-only access to the local Langfuse Postgres for trace inspection (`/trace` command) and checkpointer state debugging. | `npx -y @bytebase/dbhub --readonly --dsn ...` |
| **playwright** | Browser automation for end-to-end UI tests in Phase 9 (Vercel deploy verification, chat streaming, sources panel). | `npx -y @playwright/mcp@latest` |

**First-run approval**: Claude Code prompts once per project before loading `.mcp.json`. Approve, then `/mcp` shows the live status.

**Skipped on purpose**:
- *Official Qdrant MCP* — it's a memory store using fastembed, not a query interface for our `text-embedding-3-small` collection. Direct curl via Bash (see `/qdrant-status`) is cleaner.
- *GitHub / filesystem / fetch* — already in the user-global config, no need to redefine.

## Subagents

All six are project-scoped under `.claude/agents/`. Claude delegates automatically when a task matches the agent's `description`, or you can call one explicitly: `@rag-evaluator please run the suite`.

| Agent | When it fires | Model | Tools |
|---|---|---|---|
| **rag-evaluator** | After any retrieval / rerank / prompt / graph change. Mandatory before merging touch-the-pipeline PRs. | sonnet | Bash, Read, Glob, Grep, Edit, Write |
| **adr-writer** | When the user makes an architectural decision or says "write an ADR for X". | sonnet | Read, Write, Glob, Grep, Bash |
| **ingestion-debugger** | When a doc fails to ingest, when re-ingestion creates duplicates, when chunk counts are wrong. | sonnet | Bash, Read, Glob, Grep, Edit |
| **retrieval-tuner** | When tuning hybrid params (RRF k, BM25 weight, top-k, rerank model). Always pairs with rag-evaluator. | sonnet | Read, Edit, Grep, Glob, Bash |
| **langgraph-architect** | For any change to `apps/api/src/graph/` — adding nodes, changing edges, wiring callbacks. | **opus** (design work) | Read, Glob, Grep, Edit, Write, Bash |
| **security-auditor** | Before deploy, after any change to `main.py` / `config.py` / `security.py` / `routes/*`. Read-only. | sonnet | Read, Glob, Grep, Bash |

Each agent's full system prompt (in its `.md` file) carries the relevant constraints from BRD-01 §3.7 (the 11 mandatory technology conditions) so the agent doesn't need to re-derive them.

## Slash commands

| Command | Argument | What it does |
|---|---|---|
| `/eval [filter]` | optional | Delegates to `rag-evaluator`. Reports verdict + delta table. |
| `/ingest-test <path>` | required | Ingests a doc, then re-ingests, proves idempotency (MTC-02). |
| `/trace [session_id\|recent]` | optional | Pulls Langfuse traces via the postgres MCP, summarizes spans, highlights latency budget violations. |
| `/adr <decision>` | required | Delegates to `adr-writer`. Drafts MADR-format ADR. |
| `/milestone <N>` | required | Runs the exit checks for milestone N (1–15) from `plan.md` §Phase 11. |
| `/qdrant-status` | none | Dumps collections + dimensions + point counts + MTC-01/MTC-11 sanity. |

## Workflow recipes

**Adding a new retrieval feature**
1. `@retrieval-tuner` — design the param change, pick the experiment
2. Implement the change
3. `/eval` — `rag-evaluator` verdict gates the merge
4. If the change is structural, `/adr Add {feature}`

**Debugging a failed ingestion**
1. `/ingest-test path/to/bad-doc.pdf` — confirms the failure
2. `@ingestion-debugger` — traces stage by stage, returns root cause + fix
3. After fix, re-run `/ingest-test`

**Pre-deploy gate (Phase 9)**
1. `@security-auditor` — verifies all 11 MTCs are enforced in code
2. `/eval` — `rag-evaluator` confirms no regression
3. `/milestone 13` — runs deploy-readiness checks
4. Deploy

**Milestone completion**
1. `/milestone <N>` — verifies exit criteria
2. If COMPLETE: `/commit feat: complete milestone N — {title}`
3. Move to next milestone

## Adding more

- **New subagent**: drop `.claude/agents/{name}.md` with required `name` + `description` frontmatter.
- **New slash command**: drop `.claude/commands/{name}.md` with `description` and optional `argument-hint`, `allowed-tools`. Use `$ARGUMENTS` for input.
- **New MCP server**: edit `.mcp.json`, add an entry under `mcpServers`, restart Claude Code.

Documentation references:
- Subagents: <https://code.claude.com/docs/en/sub-agents>
- Slash commands / skills: <https://code.claude.com/docs/en/slash-commands>
- MCP: <https://code.claude.com/docs/en/mcp>
