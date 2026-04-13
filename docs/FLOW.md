# danny_rag — How the App Works (Operator Guide)

This is a read-through for someone who already has the stack running (`./dev.sh`) and now wants to understand what actually happens when a document is ingested or a user asks a question — and what to do day-to-day to keep the system useful.

---

## 1. Big Picture

```
          ┌─── ingest (CLI or HTTP) ─────┐
          │                               ▼
  You ──► Loader ──► Chunker ──► Embedder ──► Qdrant (vectors + BM25)
                                                    │
                                                    ▼
  User ─► Next.js UI ─► /api/chat ─► FastAPI /chat ─► LangGraph
                                                         │
                   rewrite → retrieve (hybrid) → rerank → generate → self_grade
                                                         │                     │
                                                         ▼                     ▼
                                                    top-5 chunks         score < 0.7?
                                                                         loop once back
                                                                                │
                                                                         answer + citations
                                                                                │
                                              ◄──── SSE stream ─────────────────┘
                                                         │
                                                    Langfuse trace
```

Two flows share one store:

- **Flow A — Ingestion**: files on disk → chunks → embeddings → Qdrant. Happens offline, any time.
- **Flow B — Chat**: a question → retrieve from Qdrant → grade answer → stream back. Happens live.

Everything in the middle is glued together by **LangGraph** (the query pipeline) and observed by **Langfuse** (every node is a traced span).

---

## 2. Service Map

`./dev.sh` boots 7 docker containers plus the api and web processes.

| What                | Where                                       | Role                                                    |
| ------------------- | -------------------------------------------- | ------------------------------------------------------- |
| **qdrant**          | http://localhost:6333/dashboard              | Vector store. Also the source of truth for BM25.        |
| **postgres**        | `localhost:5433`                             | Langfuse metadata + LangGraph checkpointer.             |
| **clickhouse**      | `localhost:8123`                             | Langfuse v3 trace rows.                                 |
| **redis**           | `localhost:6380`                             | Langfuse v3 queue + cache.                              |
| **minio**           | http://localhost:9091                        | Langfuse blob/event storage. `minio` / `miniosecret`.   |
| **langfuse-web**    | http://localhost:3002                        | Traces UI. Login `dev@local.dev` / `dev-password-change-me`. |
| **langfuse-worker** | `localhost:3030`                             | Drains Redis → ClickHouse.                              |
| **api (uvicorn)**   | http://localhost:8000                        | FastAPI — `/health`, `/chat`, `/ingest`, `/search`.     |
| **web (next)**      | http://localhost:3000                        | Chat UI.                                                |

Quick liveness smoke test:

```bash
curl http://localhost:8000/health                 # {"status":"ok",...}
curl http://localhost:6333/collections | jq .     # qdrant collections
open  http://localhost:3002                        # langfuse UI
open  http://localhost:3000                        # chat UI
```

---

## 3. Flow A — Ingestion

What happens when you add a document. Each step points at the code so you can dig deeper.

1. **Kick off.**
   - CLI: `apps/api/src/ingestion/cli.py` → `uv run python -m src.ingestion.cli <file>`.
   - HTTP: `POST /ingest` in `apps/api/src/routes/ingest.py`. Guards: API key (**MTC-07**), 5/min rate limit (**MTC-08**), 25 MB upload cap, MIME allowlist, 60s timeout, max 2 concurrent jobs (**MTC-09**).

2. **Load text.** `apps/api/src/ingestion/loaders.py:load_document()`.
   - `.pdf` → `unstructured.partition_pdf`
   - `.html` / `.htm` → BeautifulSoup text extraction
   - `.md` / `.markdown` / `.txt` → `read_text`
   - Empty content → hard fail.

3. **Derive a stable `doc_id`.** `apps/api/src/ingestion/chunker.py:derive_doc_id()` — `sha256(source_uri)[:16]`. HTTP uploads use `upload://<filename>` so the same filename always dedupes; CLI uses the absolute path (watch out — ingesting the same file from two different paths will create two docs).

4. **Chunk.** `chunker.py:chunk_document()`.
   - 512 tokens per chunk, 64-token overlap, `cl100k_base` tokenizer.
   - Each chunk gets a deterministic `point_id = UUID5(doc_id + index)` and a `content_hash = sha256(chunk_text)` — this is what makes re-ingest idempotent.

5. **Pick the embedder.** `apps/api/src/llm/factory.py:get_embedder()`.
   - `EMBED_PROVIDER=openai` → `text-embedding-3-small` (1536d, paid ~$0.02 / 1M tokens)
   - `EMBED_PROVIDER=ollama` → `nomic-embed-text` (768d, **free**, needs `ollama pull nomic-embed-text`)
   - **MTC-01**: the collection name encodes the embedder. Changing provider silently switches collections — your old corpus becomes invisible until you switch back.

6. **Ensure the Qdrant collection exists.** `apps/api/src/ingestion/pipeline.py:ensure_collection()` creates it on first run with cosine distance. One-time.

7. **Idempotency check (MTC-02).** `pipeline.py:ingest_document()` retrieves existing points by `point_id`, compares `content_hash`, and only upserts chunks whose hash differs. Re-running the same file → `upserted=0, skipped_unchanged=N`.

8. **Embed + upsert.** Changed chunks are embedded in a batch and written to Qdrant with `wait=True`.

9. **Invalidate BM25 cache.** `apps/api/src/retrieval/sparse.py:invalidate_bm25_cache()`. Next sparse query rebuilds the in-memory BM25 index from the live collection.

**Common gotchas**
- Wrong `EMBED_PROVIDER` → writes to a *different* collection, not the one the chat flow reads.
- CLI uses absolute paths for `source_uri` → the same file at two locations = two `doc_id`s. For a shared folder, keep a canonical location.
- BM25 is rebuilt lazily on the first sparse query after invalidation. First query after a big ingest is slower.

---

## 4. Flow B — Chat (Question → Grounded Answer)

1. **UI input.** `apps/web/src/components/chat/message-input.tsx` → `apps/web/src/lib/use-conversations.ts:send()`. The UI stores the user message + an empty assistant message in localStorage and captures `session_id` (persists across retries).

2. **Browser → Next proxy.** POST `/api/chat` with `{question, session_id}`. `apps/web/src/app/api/chat/route.ts` attaches the `X-API-Key` **server-side** and forwards to FastAPI. MTC-07: the API key never touches the browser.

3. **FastAPI gate.** `apps/api/src/routes/chat.py`.
   - `require_api_key` (constant-time compare in `security.py`) — MTC-07.
   - Rate-limit 20/min/IP — MTC-08.
   - Generates a new `session_id` if one isn't supplied, then streams `_event_stream()` as SSE.
   - Free-text (`question`) is never logged verbatim — `hash_text()` emits `sha256:<12hex>:len=<n>` so operators can still group repeat requests.

4. **LangGraph invoke.** `apps/api/src/graph/build.py` runs the state machine with a Langfuse callback attached. To make the LangChain callback spans and the `@observe()`-decorated LLM spans share **one** trace, `_event_stream()` wraps `graph.astream()` in an enclosing OTEL span via `lf.start_as_current_observation(name="chat-turn", input={"q_hash": ...})` plus `propagate_attributes(session_id=..., user_id="anonymous", tags=[env, llm_provider])`. Without this wrapper each provider call would create its own root trace and session/tags would never attach (Langfuse v4 behavior).

**Graph nodes** (`apps/api/src/graph/nodes.py`):

| Node            | What it does                                                                                                 |
| --------------- | ------------------------------------------------------------------------------------------------------------ |
| `rewrite_query` | Short LLM call (max 128 tok) — rewrites the question for better retrieval.                                   |
| `retrieve`      | **Hybrid search** — see below.                                                                               |
| `rerank`        | Cross-encoder (`BAAI/bge-reranker-base`) scores top-50 query/chunk pairs → keeps top-5.                      |
| `generate`      | Streams the answer with citations. Grounding prompt from **MTC-04**. `max_tokens ≤ 1024` (**MTC-10**).       |
| `self_grade`    | Tiny LLM call (max 8 tok) — returns faithfulness `0.0–1.0`.                                                  |

**Conditional edge `should_retry`:** if `grounding_score < 0.7` AND `rewrite_count < 2`, loop back to `rewrite_query` (one retry max). Else END.

**Hybrid search breakdown** (the `retrieve` node):

```
query
  ├── dense  → apps/api/src/retrieval/dense.py   → embed → qdrant.query_points(limit=50)
  ├── sparse → apps/api/src/retrieval/sparse.py  → BM25Okapi over live collection → top-50
  └── fuse   → apps/api/src/retrieval/hybrid.py  → RRF with k=60 (MTC-03) → top-50
                                                 → rerank → top-5
```

5. **SSE stream back.** Nodes emit `start / token / citations / grade / retry / done / error` events. Frontend parses in `use-conversations.ts:parseSseChunk()` and patches the assistant message live. `retry` events reset the streamed content so the user sees one clean answer after the loop.

6. **Observability + PII posture.** Every node is a Langfuse span; `@observe` on the LLM provider records token usage; `session_id` groups the full conversation; thumbs up/down in the UI posts back as a Langfuse score. Open http://localhost:3002 → Traces to watch it in real time.

   **Free-text is redacted on the way out**, two layers deep, so neither logs nor the Langfuse store ever see raw user questions, rewritten queries, retrieved context, or model answers:

   - `apps/api/src/observability/redact.py:mask_payload()` is registered as the Langfuse client's global `mask=` hook (`observability/langfuse.py`). It replaces every span `input` / `output` payload with `<redacted>` before it leaves the process. Token counts, model names, span shape, timings, and scores are untouched — only the free-text blobs are nuked.
   - Provider `@observe()` decorators in `llm/anthropic.py`, `llm/openai.py`, and `llm/ollama.py` pass `capture_input=False, capture_output=False` so the messages list and the generated string are never handed to Langfuse in the first place (defense in depth — if `mask_payload` ever regresses, nothing leaks).
   - INFO logs in `routes/chat.py`, `routes/search.py`, and `graph/nodes.py:rewrite_query` use `hash_text()` instead of `%r` for questions and rewrites. What you see in `uvicorn` stdout is `q=sha256:a1b2c3d4e5f6:len=42` — enough to correlate, impossible to read.

   Trade-off: because input/output is masked, the Langfuse UI no longer shows the actual question or answer on a trace — you see the DAG, timings, token counts, and the `q_hash`. For debugging a specific user complaint, correlate via `session_id` and the `q_hash` from the API logs.

---

## 5. Tasker Task List

Copy-paste-ready. Each task says **do this**, **verify that**, and **which part of the flow you just exercised**.

### T1 — Cold boot the stack
- **Do:** `./dev.sh` from repo root.
- **Verify:** `curl http://localhost:8000/health` → `{"status":"ok",...}`; http://localhost:6333/dashboard loads; http://localhost:3002 login works.
- **Exercises:** service map.

### T2 — Ingest one document
- **Do:** drop a file into `data/` (e.g. `data/handbook.md`), then:
  ```bash
  cd apps/api && uv run python -m src.ingestion.cli ../../data/handbook.md
  ```
- **Verify:** log shows `upserted=N skipped_unchanged=0`; Qdrant dashboard shows `N` new points in the active collection.
- **Exercises:** Flow A steps 1–9.

### T3 — Prove idempotency (MTC-02)
- **Do:** re-run the exact same command from T2.
- **Verify:** log shows `upserted=0 skipped_unchanged=N`; Qdrant point count is identical.
- **Exercises:** Flow A step 7. **This is a hard project invariant — if this ever fails, stop and investigate with the `ingestion-debugger` subagent.**

### T4 — Ingest a folder
- **Do:**
  ```bash
  cd apps/api
  for f in ../../data/corpus/*.{pdf,md,txt}; do
    uv run python -m src.ingestion.cli "$f"
  done
  ```
- **Verify:** run `/qdrant-status` (slash command) or `curl http://localhost:6333/collections/<name>/points/count` — point count matches sum of chunks.
- **Exercises:** whole ingestion pipeline in bulk.

### T5 — Ask a question end-to-end
- **Do:** open http://localhost:3000, ask a question that's answerable from the corpus.
- **Verify:**
  - Answer streams token-by-token in the UI.
  - Citations panel shows `doc_id` + snippet per source.
  - http://localhost:3002 → Traces → newest trace has spans `rewrite_query → retrieve → rerank → generate → self_grade`.
- **Exercises:** Flow B end-to-end.

### T6 — Force a refusal
- **Do:** ask something clearly outside the corpus ("what's the capital of Mars?").
- **Verify:** the model replies with the BRD-mandated **"I don't have enough information to answer that"**. The Langfuse trace shows a low `grounding_score`.
- **Exercises:** MTC-04 grounding prompt.

### T7 — Watch a retry
- **Do:** ask a borderline question (vague phrasing, partial match). Watch the UI — you may see a "retrying..." flash.
- **Verify:** Langfuse trace has **two** `rewrite_query` spans and `rewrite_count = 1`.
- **Exercises:** `should_retry` conditional edge.

### T8 — Give feedback
- **Do:** click thumbs up or thumbs down on an answer.
- **Verify:** Langfuse trace → Scores tab shows the new score attached to the session.
- **Exercises:** feedback loop.

### T9 — Run the eval suite
- **Do:**
  ```bash
  cd apps/api && uv run pytest evals/ -v
  # or the slash command:
  /eval
  ```
- **Verify:** report runs against the curated dataset. Thresholds: Faithfulness ≥ 0.85, Hallucination ≤ 0.10, AnswerRelevancy ≥ 0.70.
- **When to run:** after *any* change to retrieval, reranking, the generator prompt, or the eval dataset. Non-negotiable before merging retrieval changes.

### T10 — Free mode (optional, no API cost)
- **Do:** in `apps/api/.env`, set:
  ```
  LLM_PROVIDER=ollama
  EMBED_PROVIDER=ollama
  ```
  Then `ollama pull nomic-embed-text` and a chat model (e.g. `ollama pull llama3.2`). Restart the api.
- **Verify:** re-run T2 — it now writes to a **different** Qdrant collection (768d vs 1536d, per MTC-01/11). Your old corpus is invisible until you switch back. No API charges.
- **Exercises:** provider switch + collection-per-dim invariant.

### T11 — Shut down cleanly
- **Do:** Ctrl-C the `dev.sh` process, then:
  ```bash
  docker compose down
  ```
- **Verify:** `docker ps` shows no `danny_rag-*` containers; no orphaned `uvicorn` or `next` processes (`ps aux | grep -E 'uvicorn|next'`).

---

## 6. Cheat Sheet

**URLs**

| Target            | URL                                        | Login                                                 |
| ----------------- | ------------------------------------------ | ----------------------------------------------------- |
| Chat UI           | http://localhost:3000                      | —                                                     |
| API               | http://localhost:8000                      | `X-API-Key: dev-local-key-change-me`                  |
| Qdrant dashboard  | http://localhost:6333/dashboard            | —                                                     |
| Langfuse          | http://localhost:3002                      | `dev@local.dev` / `dev-password-change-me`            |
| MinIO console     | http://localhost:9091                      | `minio` / `miniosecret`                               |

**Env vars that change behavior** (`apps/api/.env`, read by `apps/api/src/config.py`)

| Var                       | Effect                                                       |
| ------------------------- | ------------------------------------------------------------ |
| `LLM_PROVIDER`            | `anthropic` / `openai` / `ollama` — which model answers chats. |
| `EMBED_PROVIDER`          | `openai` / `ollama` — which embedder runs, **and which Qdrant collection is used**. |
| `QDRANT_URL`              | Vector store endpoint.                                       |
| `QDRANT_COLLECTION`       | Usually derived from `EMBED_PROVIDER`; override with care.   |
| `API_KEY`                 | The `X-API-Key` header value.                                |
| `ALLOWED_ORIGINS`         | CORS allowlist. **Never `*`** — MTC-06.                      |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | Trace destination. Matches docker-compose init values for local. |

**MTCs referenced in this doc** (BRD-01 §3.7 — all non-negotiable)

| MTC    | In one line                                                              |
| ------ | ------------------------------------------------------------------------ |
| MTC-01 | One Qdrant collection per embedding model — no dim mixing.               |
| MTC-02 | Re-ingesting the same content produces zero new points.                  |
| MTC-03 | Hybrid: dense + BM25 + RRF(k=60) then rerank top-50 → top-5. No dense-only. |
| MTC-04 | Grounding prompt is verbatim from the BRD and binding.                   |
| MTC-06 | CORS is an explicit allowlist, never `*`.                                |
| MTC-07 | API key required on `/chat` and `/ingest`. `/health` is public.          |
| MTC-08 | Rate limits: 20/min chat, 5/min ingest, per IP.                          |
| MTC-09 | Upload guards: 25 MB cap, MIME allowlist, 60s timeout, 2-job semaphore.  |
| MTC-10 | `max_tokens = 1024` hard ceiling at the provider layer.                  |
| MTC-11 | `text-embedding-3-small` locked at 1536d — switching embedders requires an ADR. |

**When something looks wrong**

| Symptom                                                    | First thing to check                                                                 |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Re-ingesting a file keeps creating new points              | `EMBED_PROVIDER` didn't change silently? `source_uri` stable? → run `ingestion-debugger`. |
| Chat answers "I don't have enough information" for known-good questions | Collection name mismatch — probably wrong `EMBED_PROVIDER`. Check `curl http://localhost:6333/collections`. |
| Langfuse UI has no new traces                              | `LANGFUSE_*` env vars set? `langfuse-worker` healthy in `docker ps`?                 |
| Langfuse trace shows `<redacted>` for input/output         | **Expected.** `mask_payload` + `capture_input=False` nuke free-text on purpose. Use `session_id` + the `q_hash` from api logs to correlate. |
| Multiple root traces per chat turn instead of one          | The `start_as_current_observation("chat-turn")` wrapper in `routes/chat.py:_event_stream()` isn't firing — usually means `get_langfuse()` returned None (keys not set). |
| Eval regression after a retrieval tweak                    | Run `/eval` to quantify, then revert or hand to `retrieval-tuner`.                   |
