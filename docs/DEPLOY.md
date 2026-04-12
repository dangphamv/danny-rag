# Deploy runbook — danny_rag

End-to-end procedure to take this repo from `git push` to a working production chat at a public URL.

**Estimated time**: ~90 minutes for a first deploy. Subsequent deploys are auto-pushed.

**Estimated monthly cost**: <$30 (BRD-01 §13.1 budget) — Railway hobby + Vercel hobby + Qdrant Cloud free + LLM API spend.

## Architecture overview

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   browser    │─────────│  Vercel          │─────────│  Railway         │
│              │  HTTPS  │  Next.js 15      │  HTTPS  │  FastAPI api     │
└──────────────┘         │  /api/chat proxy │  +API   │  + Langfuse stack│
                         │  (server-side    │  key    │                  │
                         │   API key inject)│         │  Postgres+CH+    │
                         └──────────────────┘         │  Redis+MinIO     │
                                                      └────────┬─────────┘
                                                               │
                                                      ┌────────▼─────────┐
                                                      │  Qdrant Cloud    │
                                                      │  (free 1 GB)     │
                                                      └──────────────────┘
```

Three external surfaces:

1. **Vercel** — hosts `apps/web` (Next.js). Public URL: `https://<your-project>.vercel.app`
2. **Railway** — hosts `apps/api` (FastAPI) **and** the Langfuse v3 stack as a separate Railway project
3. **Qdrant Cloud** — managed vector store, free 1 GB cluster

## Prerequisites

- GitHub repo with this codebase pushed to a branch you control (typically `main`)
- Railway account: <https://railway.app>
- Vercel account: <https://vercel.com>
- Qdrant Cloud account: <https://cloud.qdrant.io>
- Anthropic API key: <https://console.anthropic.com>
- OpenAI API key: <https://platform.openai.com>
- Local: `gh`, `railway`, `vercel` CLIs installed (`brew install gh railway && pnpm add -g vercel`)

## Step 1 — Qdrant Cloud (5 minutes)

1. Sign in to <https://cloud.qdrant.io>
2. Create a new free 1 GB cluster, region close to where Railway will run (`us-east-1` is a safe default)
3. From the cluster page, copy:
   - **URL** (e.g. `https://abc-xyz.us-east-0-0.aws.cloud.qdrant.io`)
   - **API key**
4. Save both — Railway env vars in step 3 below.

You do **not** seed the corpus yet. That happens in step 5 once the API is reachable.

## Step 2 — Langfuse on Railway (15 minutes)

Langfuse v3 needs Postgres + ClickHouse + Redis + MinIO + langfuse-web + langfuse-worker (per ADR-0009). Use Railway's official template — do NOT try to deploy these one service at a time.

1. Visit <https://railway.app/template/langfuse-v3> (or the latest Langfuse template URL from <https://langfuse.com/self-hosting>)
2. Click **Deploy on Railway**
3. Pick a project name like `danny-rag-langfuse`
4. Railway provisions all 6 services + a public URL for `langfuse-web`. Wait for the green check (~5 minutes — ClickHouse migrations are the slow part)
5. Open the Langfuse public URL, sign up for the org/project. Note:
   - **Public URL** (e.g. `https://danny-rag-langfuse.up.railway.app`)
   - **Project Public Key** (from Project Settings → API Keys → create a pair)
   - **Project Secret Key** (same place)

Save all three — they go into the API service env vars in step 3.

## Step 3 — FastAPI backend on Railway (20 minutes)

1. Create a **separate Railway project** (not the Langfuse one): `danny-rag-api`
2. Connect it to your GitHub repo
3. **Set the Root Directory to `apps/api`** in the project's settings — Railway will only watch this subtree
4. Railway detects `apps/api/Dockerfile` and `apps/api/railway.toml` automatically. The build will start once root directory is set
5. Set environment variables (Variables tab):

   | Key | Value |
   |---|---|
   | `ENV` | `production` |
   | `LLM_PROVIDER` | `anthropic` |
   | `EMBED_PROVIDER` | `openai` |
   | `ANTHROPIC_API_KEY` | from console.anthropic.com |
   | `OPENAI_API_KEY` | from platform.openai.com |
   | `QDRANT_URL` | from step 1 |
   | `QDRANT_API_KEY` | from step 1 |
   | `LANGFUSE_HOST` | from step 2 |
   | `LANGFUSE_PUBLIC_KEY` | from step 2 |
   | `LANGFUSE_SECRET_KEY` | from step 2 |
   | `API_KEY` | a fresh random string — `openssl rand -hex 32` |
   | `ALLOWED_ORIGINS` | comma-sep list of Vercel domains — fill in step 6 below |

   Postgres is not needed for the api service (Langfuse has its own instance from step 2; the LangGraph checkpointer is wired but not yet activated — see ADR-0005).

6. Deploy. Wait for the build (~5-10 minutes — first build downloads the cross-encoder model)
7. Railway gives you a public URL like `https://danny-rag-api.up.railway.app`. Verify:

   ```bash
   curl -sf https://danny-rag-api.up.railway.app/health
   # {"status": "ok", "version": "0.1.0", "env": "production"}
   ```

## Step 4 — Vercel frontend (10 minutes)

1. From `apps/web/`:

   ```bash
   cd apps/web
   vercel link
   ```

   When prompted, create a new project. Choose Next.js framework. **Set the Root Directory to `apps/web`** when asked.

2. Set environment variables in the Vercel dashboard (Project → Settings → Environment Variables):

   | Key | Scope | Value |
   |---|---|---|
   | `API_URL` | Production, Preview | from step 3 (Railway api URL) |
   | `API_KEY` | Production, Preview | the same fresh random string from step 3 |

   **No `NEXT_PUBLIC_API_KEY`.** The API key is server-side only — see BRD-01 §3.7 MTC-07 and the proxy implementation in `apps/web/src/app/api/chat/route.ts`. The `security-auditor` subagent verifies this.

3. Deploy:

   ```bash
   vercel --prod
   ```

   Vercel gives you a public URL like `https://danny-rag-web.vercel.app`. Note both prod and preview URL patterns.

## Step 5 — Wire CORS and seed the corpus (10 minutes)

### 5a. CORS (MTC-06)

Vercel preview URLs follow the pattern `https://<project>-<branch>-<account>.vercel.app`. The backend's `ALLOWED_ORIGINS` must list every origin you want to talk to it. **No `*`** — that's MTC-06.

Update Railway env var (the api project, not Langfuse):

```
ALLOWED_ORIGINS=https://danny-rag-web.vercel.app,https://danny-rag-web-git-main-yourname.vercel.app
```

Railway re-deploys on env change. Verify CORS is correct by opening the prod web URL — the chat should work without any browser-console CORS errors.

### 5b. Seed the corpus

Production Qdrant is empty. Re-ingest from local against the cloud URL. **Do NOT try to snapshot local Docker Qdrant into Cloud** — re-ingestion is cleaner and exercises the prod ingestion path (BRD-01 §9 deployment plan).

```bash
cd apps/api

# Point at Qdrant Cloud + your prod LLM/embedding keys.
export QDRANT_URL=<from step 1>
export QDRANT_API_KEY=<from step 1>
export OPENAI_API_KEY=<your prod key>

uv run python -m src.ingestion.cli ../../data/sample.txt
# Expect: total_chunks=N upserted=N skipped_unchanged=0
```

Re-run the same command — should report `upserted=0 skipped_unchanged=N`. That's MTC-02 (idempotency) verified against prod.

Repeat for any other documents you want in the production corpus.

## Step 6 — End-to-end smoke test

Open `https://danny-rag-web.vercel.app` in a browser. Ask a question grounded in the corpus you ingested in step 5b. Expect:

1. Tokens stream in
2. The sources panel populates with chunks from your ingested documents
3. The grounding score badge appears (M10 self-grading)
4. Open Langfuse at the URL from step 2 — no traces yet (the Langfuse callback isn't wired into the graph yet — see "Known gaps" below)

## Step 7 — Spend alerts (manual checklist, mandatory per BRD-01 §10 R1)

This is **not code**. It is a checklist item.

1. <https://console.anthropic.com> → Settings → Limits & Usage → set a monthly cap (suggest $20)
2. <https://platform.openai.com> → Usage → Limits → set a monthly hard cap (suggest $20)
3. Note both in your password manager / project tracker. They MUST be set before the prod URL goes wider than you.

## Step 8 — Configure GitHub secrets for CI

The `eval.yml` and `web-ci.yml` / `api-ci.yml` workflows need these secrets in the repo:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

Set them in **Settings → Secrets and variables → Actions**.

## Auto-deploys after first deploy

- **Railway api**: any push to `main` that touches `apps/api/**` triggers a rebuild
- **Vercel web**: any push to `main` triggers a build; PRs get preview URLs
- **Eval workflow**: nightly cron at 07:00 UTC + on PRs touching retrieval/graph/llm/ingestion paths

## Known gaps to fix in a follow-up deploy

These are open issues you'll hit but aren't blockers for getting the prod URL working:

1. ~~Langfuse callback not yet wired into the LangGraph execution~~ ✅ **Fixed.** `chat.py:_build_graph_config()` constructs a `{"callbacks": [CallbackHandler()], "metadata": {...}}` config and passes it to `graph.astream()`. Per-node spans appear automatically. LLM-call spans come from `@observe()` decorators on `AnthropicProvider`/`OpenAIProvider`/`OllamaProvider` `generate`/`astream`. Traces are tagged with `langfuse_session_id`, env, and llm_provider for filtering.
2. **`numReplicas = 1` in `railway.toml`** — single-replica limits the in-process semaphore (MTC-09) to 2 concurrent ingestions globally. If you scale to 2+ replicas, the semaphore becomes per-replica → 4 total. ADR-0010 mitigation triggers note this; move the semaphore to Redis if you scale out.
3. **Qdrant Cloud free tier** caps at 1 GB. ~500k chunks at 1536d. The `/qdrant-status` slash command shows current usage.
4. **Postgres checkpointer is wired but inactive**. Sessions don't survive Railway restarts. To activate: pass `checkpointer=AsyncPostgresSaver(...)` to `get_compiled_graph()` and add a `POSTGRES_URL` env var pointing at the Langfuse Postgres instance (re-uses the shared instance per ADR-0010).
5. **BRD v1.2 update for Langfuse v3** — the BRD §7.2 BRD.01.3205 still says "single-binary Railway deploy" which was true for Langfuse v2 but is wrong for v3. The runbook above documents the v3 reality; the BRD should be bumped to match. Flagged in ADR-0009.

## Rollback

- **Vercel**: Deployments tab → previous deploy → Promote to Production
- **Railway api**: Deployments tab → previous deploy → Redeploy
- **Langfuse**: Deployments tab on the Langfuse project → previous deploy → Redeploy

Qdrant Cloud has no built-in rollback — re-ingest from a known-good corpus to recover.

## Local-prod parity

The Dockerfile in `apps/api/` produces the same image Railway runs. You can test it locally:

```bash
cd apps/api
docker build -t danny-rag-api .
docker run --rm -p 8000:8000 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e QDRANT_URL=$QDRANT_URL \
  -e QDRANT_API_KEY=$QDRANT_API_KEY \
  -e API_KEY=test-key \
  -e ALLOWED_ORIGINS=http://localhost:3000 \
  danny-rag-api

# Same /health check
curl -sf http://localhost:8000/health
```

This catches Dockerfile issues before pushing to Railway.

## Cost watching

| Service | Tier | Monthly cost (hobby) |
|---|---|---|
| Railway (api service) | hobby | ~$5 |
| Railway (Langfuse stack — 6 services) | hobby | ~$10-15 |
| Vercel (Next.js) | hobby | $0 |
| Qdrant Cloud (1 GB cluster) | free | $0 |
| OpenAI (embeddings + DeepEval judge) | pay-as-you-go | ~$2-5 |
| Anthropic (chat) | pay-as-you-go | ~$5-15 |
| **Total target** | | **<$30/month** |

The biggest budget risk is the Langfuse stack (6 services). If hobby tier won't fit, downgrade by:
- Splitting Langfuse to its own Railway project so it gets its own free hours quota
- Using Langfuse Cloud free tier as a temporary bridge (loses self-hosted property — see ADR-0009)
