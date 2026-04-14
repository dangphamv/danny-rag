# Deploy checklist — danny_rag

Operational twin of [`DEPLOY.md`](./DEPLOY.md). Walk top-to-bottom, tick every box, paste captured values into the fenced blocks so later steps can copy them back.

Target: one working prod URL. Estimated time ~90 min. Estimated monthly cost <$30 (BRD-01 §13.1).

---

## Pre-flight

- [ ] GitHub repo pushed: `dangphamv/danny-rag` on `main`
- [ ] Anthropic API key in hand — <https://console.anthropic.com>
- [ ] OpenAI API key in hand — <https://platform.openai.com>
- [ ] Qdrant Cloud account — <https://cloud.qdrant.io>
- [ ] Railway account — <https://railway.app>
- [ ] Vercel account — <https://vercel.com>
- [ ] CLIs installed: `gh`, `railway`, `vercel` (`brew install gh railway && pnpm add -g vercel`)
- [ ] Logged in: `gh auth status`, `railway whoami`, `vercel whoami`

---

## Step 1 — Qdrant Cloud (5 min)

- [ ] Sign in to <https://cloud.qdrant.io>
- [ ] Create free 1 GB cluster, region `us-east` (match Railway default)
- [ ] Cluster status green
- [ ] Copy the cluster URL
- [ ] Generate + copy an API key

**Captured values**

```
QDRANT_URL=
QDRANT_API_KEY=
```

Do not snapshot local Docker Qdrant into Cloud — the corpus is re-ingested in step 5b, which also exercises MTC-02 idempotency against prod.

---

## Step 2 — Langfuse v3 on Railway (15 min)

Langfuse v3 is 6 services (Postgres + ClickHouse + Redis + MinIO + langfuse-web + langfuse-worker). Deploy the **template as a unit** — do not build service-by-service.

- [ ] Open <https://railway.app/template/langfuse-v3> (or the current template link from <https://langfuse.com/self-hosting>)
- [ ] Click **Deploy on Railway**
- [ ] Project name: `danny-rag-langfuse`
- [ ] Wait ~5 min for all 6 services green (ClickHouse migrations are the slow part)
- [ ] Open `langfuse-web` public URL, sign up, create org + project
- [ ] Project Settings → API Keys → create a key pair

**Captured values**

```
LANGFUSE_HOST=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
```

---

## Step 3 — FastAPI backend on Railway (20 min)

- [ ] Generate the shared API key — **save this, you need it again in step 4**:

  ```bash
  openssl rand -hex 32
  ```

- [ ] New Railway project `danny-rag-api`, connect to `dangphamv/danny-rag`
- [ ] **Settings → Root Directory = `apps/api`** (Railway auto-detects [`apps/api/Dockerfile`](../apps/api/Dockerfile) + [`apps/api/railway.toml`](../apps/api/railway.toml))
- [ ] Variables tab — paste the following, filling values from steps 1, 2, and the `openssl` output. Env var names are the source of truth per [`apps/api/src/config.py`](../apps/api/src/config.py):

  | Key | Value |
  |---|---|
  | `ENV` | `production` |
  | `LLM_PROVIDER` | `anthropic` |
  | `EMBED_PROVIDER` | `openai` |
  | `ANTHROPIC_API_KEY` | from pre-flight |
  | `OPENAI_API_KEY` | from pre-flight |
  | `QDRANT_URL` | from step 1 |
  | `QDRANT_API_KEY` | from step 1 |
  | `LANGFUSE_HOST` | from step 2 |
  | `LANGFUSE_PUBLIC_KEY` | from step 2 |
  | `LANGFUSE_SECRET_KEY` | from step 2 |
  | `API_KEY` | from `openssl rand -hex 32` above |
  | `ALLOWED_ORIGINS` | leave blank for now — filled in step 5a |

- [ ] Deploy. First build takes ~5–10 min (the cross-encoder is baked into the builder stage per [`apps/api/Dockerfile`](../apps/api/Dockerfile))
- [ ] Copy the Railway public URL

**Captured values**

```
API_KEY=
RAILWAY_API_URL=
```

- [ ] Health check passes:

  ```bash
  curl -sf https://<RAILWAY_API_URL>/health
  # expected: {"status":"ok","version":"0.1.0","env":"production"}
  ```

- [ ] Unauthenticated `/chat` is rejected (MTC-07):

  ```bash
  curl -i -X POST https://<RAILWAY_API_URL>/chat
  # expected: HTTP/1.1 401
  ```

---

## Step 4 — Next.js frontend on Vercel (10 min)

- [ ] From the repo root:

  ```bash
  cd apps/web
  vercel link
  ```

- [ ] When prompted: new project, framework = Next.js, **Root Directory = `apps/web`**
- [ ] Vercel dashboard → Project → Settings → Environment Variables:

  | Key | Scope | Value |
  |---|---|---|
  | `API_URL` | Production, Preview | Railway api URL from step 3 |
  | `API_KEY` | Production, Preview | same `openssl` value from step 3 |

- [ ] **No `NEXT_PUBLIC_API_KEY`.** Key stays server-side — injected in [`apps/web/src/app/api/chat/route.ts`](../apps/web/src/app/api/chat/route.ts) before proxying to FastAPI (MTC-07)
- [ ] Deploy:

  ```bash
  vercel --prod
  ```

- [ ] Copy the Vercel prod URL

**Captured values**

```
VERCEL_PROD_URL=
VERCEL_PREVIEW_URL_PATTERN=
```

The preview URL pattern is `https://<project>-git-<branch>-<account>.vercel.app`. You need both for step 5a.

---

## Step 5a — Wire CORS (MTC-06)

CORS is enforced in [`apps/api/src/main.py:46-53`](../apps/api/src/main.py) — explicit allowlist, no `*`.

- [ ] Update the `ALLOWED_ORIGINS` env var on the Railway **api** project (not Langfuse) to a comma-separated list:

  ```
  ALLOWED_ORIGINS=https://<VERCEL_PROD_URL>,https://<project>-git-main-<account>.vercel.app
  ```

- [ ] Railway auto-redeploys (~1 min). Wait for green
- [ ] Browser hits to the Vercel URL show no CORS errors in the console
- [ ] Foreign origin is rejected:

  ```bash
  curl -i -H "Origin: https://evil.example.com" https://<RAILWAY_API_URL>/health
  # expected: no "Access-Control-Allow-Origin: *" header
  ```

---

## Step 5b — Seed the corpus

Production Qdrant is empty. Re-ingest from local against the cloud URL.

- [ ] Export prod vars locally:

  ```bash
  cd apps/api
  export QDRANT_URL="<from step 1>"
  export QDRANT_API_KEY="<from step 1>"
  export OPENAI_API_KEY="<prod key>"
  ```

- [ ] First ingest — expect `upserted=N`:

  ```bash
  uv run python -m src.ingestion.cli ../../data/sample.txt
  # expected: total_chunks=N upserted=N skipped_unchanged=0
  ```

- [ ] Second ingest — expect `upserted=0` (MTC-02 idempotency):

  ```bash
  uv run python -m src.ingestion.cli ../../data/sample.txt
  # expected: upserted=0 skipped_unchanged=N
  ```

- [ ] `/qdrant-status` slash command confirms collection `chunks_text-embedding-3-small` exists with dimension 1536 (MTC-01 / MTC-11)

If the second run reports `upserted > 0`, stop and invoke the `ingestion-debugger` subagent.

Repeat for any other docs that belong in the production corpus.

---

## Step 6 — End-to-end smoke test

- [ ] Open `https://<VERCEL_PROD_URL>` in a browser
- [ ] Ask a question grounded in the seeded corpus
- [ ] Tokens stream in
- [ ] Sources panel populates with chunks
- [ ] Grounding score badge appears (M10 self-grading)
- [ ] Langfuse UI shows a trace per chat turn with spans for `rewrite → retrieve → rerank → generate → self_grade` plus nested LLM-call spans (from `@observe()` decorators in [`apps/api/src/llm/anthropic.py`](../apps/api/src/llm/anthropic.py))
- [ ] Langfuse trace is tagged with `env=production` and `llm_provider=anthropic`

If any of the above fail, run `/trace <session_id>` to inspect the trace directly.

---

## Step 7 — Spend caps (mandatory, BRD-01 §10 R1)

**Do NOT share the Vercel URL with anyone until both caps are set.**

- [ ] Anthropic: <https://console.anthropic.com> → Settings → Limits & Usage → monthly cap set
  - [ ] Cap value: `$20` (suggested)
- [ ] OpenAI: <https://platform.openai.com> → Usage → Limits → monthly hard cap set
  - [ ] Cap value: `$20` (suggested)
- [ ] Both values recorded in password manager / project tracker

---

## Step 8 — GitHub Actions secrets

Needed for nightly [`eval.yml`](../.github/workflows/eval.yml) and PR gates on retrieval changes.

- [ ] Set both secrets:

  ```bash
  gh secret set ANTHROPIC_API_KEY --body "<key>" --repo dangphamv/danny-rag
  gh secret set OPENAI_API_KEY    --body "<key>" --repo dangphamv/danny-rag
  ```

- [ ] Verify they landed:

  ```bash
  gh secret list --repo dangphamv/danny-rag
  # expected: ANTHROPIC_API_KEY, OPENAI_API_KEY
  ```

---

## Verification matrix

Phase 11 milestone 13 exit criteria. All 10 must be green.

| # | Check | Command / Action | Expected |
|---|---|---|---|
| 1 | API health | `curl -sf https://<RAILWAY_API_URL>/health` | `{"status":"ok","env":"production",...}` |
| 2 | API auth enforced | `curl -i -X POST https://<RAILWAY_API_URL>/chat` (no key) | `HTTP/1.1 401` |
| 3 | CORS allowlist (no `*`) | `curl -i -H "Origin: https://evil.example.com" https://<RAILWAY_API_URL>/health` | no `Access-Control-Allow-Origin: *` header |
| 4 | Qdrant seeded | `/qdrant-status` slash command | collection `chunks_text-embedding-3-small`, dim 1536, points > 0 |
| 5 | Idempotent re-ingest | second `uv run python -m src.ingestion.cli` | `upserted=0` |
| 6 | Vercel up | `curl -sf https://<VERCEL_PROD_URL>` | `200` |
| 7 | End-to-end chat | Browser: ask a grounded question | tokens stream + citations + grade badge |
| 8 | Langfuse trace | Langfuse UI filtered by `env=production` | trace with rewrite/retrieve/rerank/generate/self_grade spans |
| 9 | Spend caps | Manual: Anthropic + OpenAI consoles | both $20 caps active |
| 10 | GitHub secrets | `gh secret list --repo dangphamv/danny-rag` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` present |

- [ ] All 10 rows green → Phase 11 milestone 13 is complete

---

## Known open issues (not blocking)

Documented in [`DEPLOY.md:196-205`](./DEPLOY.md#known-gaps-to-fix-in-a-follow-up-deploy). Do not attempt to fix them inline during first deploy:

1. `numReplicas = 1` in [`apps/api/railway.toml`](../apps/api/railway.toml) — the ingestion semaphore is per-replica (MTC-09). Accepted at MVP scale.
2. Postgres checkpointer is wired but inactive — sessions don't survive Railway restarts. See ADR-0005.
3. Qdrant Cloud free tier caps at 1 GB (~500k chunks at 1536d).
4. BRD §7.2 BRD.01.3205 still says "single-binary Langfuse" (v2 era). Flagged in ADR-0009.

---

## Rollback

- **Vercel**: Deployments tab → pick a previous deploy → Promote to Production
- **Railway api**: Deployments tab → pick a previous deploy → Redeploy
- **Langfuse**: Deployments tab on the Langfuse project → Redeploy
- **Qdrant Cloud**: no built-in rollback — re-ingest from a known-good corpus
