# danny_rag api

FastAPI backend for the RAG knowledge chatbot. Python 3.12, managed by `uv`.

See `../../docs/01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md` for the full requirements and the 11 mandatory technology conditions (MTC-01 to MTC-11) this code enforces.

## Setup

```bash
# from repo root
docker compose up -d        # data plane: qdrant, postgres, langfuse, ...

# from apps/api
uv sync                     # install dependencies
uv run uvicorn src.main:app --reload --port 8000
```

Then:

```bash
curl -s http://localhost:8000/health | jq
# {"status": "ok", "version": "0.1.0", "env": "local"}
```

## Layout (current — milestones 1–12)

```
apps/api/
├── pyproject.toml
├── .python-version       # 3.12
├── README.md
├── src/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, CORS allowlist (MTC-06), rate limiter, lifespan
│   ├── config.py         # pydantic-settings — all 11 MTC defaults baked in
│   ├── security.py       # API key dependency (MTC-07)
│   ├── observability/
│   │   └── langfuse.py   # singleton client + lifespan flush
│   ├── llm/
│   │   ├── protocol.py   # Embedder + LLMProvider Protocols + Message TypedDict
│   │   ├── anthropic.py  # AnthropicProvider (claude-sonnet-4-6) — MTC-10 clamps max_tokens
│   │   ├── openai.py     # OpenAIEmbedder + OpenAIProvider (gpt-4o-mini) — MTC-10/11
│   │   ├── ollama.py     # OllamaEmbedder + OllamaProvider (llama3.1:8b) — MTC-10
│   │   └── factory.py    # get_embedder() + get_llm()
│   ├── graph/
│   │   ├── state.py      # GraphState TypedDict + Citation
│   │   ├── nodes.py      # rewrite → retrieve → rerank → generate → self_grade (M10 loop)
│   │   └── build.py      # StateGraph + conditional retry edge (cap = 1 retry)
│   ├── limits.py         # shared slowapi Limiter (MTC-08)
│   ├── ingestion/
│   │   ├── loaders.py    # PDF (unstructured), MD/HTML/TXT
│   │   ├── chunker.py    # RecursiveCharacterTextSplitter, 512/64, MTC-02 UUIDv5 point IDs
│   │   ├── pipeline.py   # ingest_document() — idempotent upsert + BM25 invalidation
│   │   └── cli.py        # python -m src.ingestion.cli <path>
│   ├── retrieval/
│   │   ├── types.py      # ScoredChunk
│   │   ├── dense.py      # Qdrant similarity (qdrant_client context manager)
│   │   ├── sparse.py     # BM25Index singleton, lazy build, invalidate hook
│   │   ├── hybrid.py     # rrf_fuse() + hybrid_search() — MTC-03
│   │   └── rerank.py     # bge-reranker-base via sentence-transformers (asyncio.to_thread)
│   └── routes/
│       ├── health.py     # GET /health (public)
│       ├── search.py     # GET /search (auth'd, default hybrid+rerank)
│       ├── chat.py       # POST /chat (auth'd, rate-limited 20/min, SSE)
│       └── ingest.py     # POST /ingest (auth'd, 5/min, MTC-09 guards)
├── tests/
│   ├── test_health.py
│   ├── test_chunker.py
│   ├── test_rrf.py
│   ├── test_graph.py        # mocked-LLM smoke test of the graph topology
│   └── test_ingest_route.py # MTC-09 guard tests (size cap, MIME, timeout)
└── evals/                   # M11: DeepEval suite, Phase 7a advisory
    ├── dataset.jsonl        # 17 cases (10 extractive, 3 multi-hop, 4 refusal)
    ├── conftest.py          # session-scoped pipeline fixture
    ├── test_answer.py       # Faithfulness, Hallucination, AnswerRelevancy + refusal contract
    ├── test_retrieval.py    # ContextualRelevancy
    ├── test_rerank.py       # cross-encoder ablation (precision lift)
    └── README.md            # how to run, thresholds, Phase 7a→7b checklist
```

## /chat endpoint (M8)

Streaming SSE chat. Per request flow: rewrite query → hybrid retrieve → cross-encoder rerank → grounded generate. Tokens stream as `data: {"type":"token","content":"..."}\n\n` events; the final `data: {"type":"citations","citations":[...]}\n\n` carries source chunks.

```bash
curl -N -H 'X-API-Key: dev-local-key-change-me' \
  -H 'Content-Type: application/json' \
  -X POST http://localhost:8000/chat \
  -d '{"question":"what is RRF and why does this project use it?"}'
```

Event sequence:

```
data: {"type":"start","session_id":"..."}
data: {"type":"token","content":"Reciprocal"}
data: {"type":"token","content":" Rank"}
...
data: {"type":"citations","citations":[{"doc_id":"...","title":"...","snippet":"...","score":0.92}, ...]}
data: {"type":"grade","score":0.85,"rewrite_count":1,"skipped":false}
data: {"type":"done"}
data: [DONE]
```

If the self-grading loop fires (M10), the sequence repeats with a `retry` marker:

```
... first answer tokens + citations ...
data: {"type":"grade","score":0.30,"rewrite_count":1,"skipped":false}
data: {"type":"retry","rewrite_count":2}
... second answer tokens + citations ...
data: {"type":"grade","score":0.88,"rewrite_count":2,"skipped":false}
data: {"type":"done"}
data: [DONE]
```

The loop is hard-capped at one retry by `should_retry()` checking `rewrite_count >= MAX_REWRITES (=2)`.

The grounding system prompt is verbatim from BRD-01 §3.7 MTC-04 and is unit-tested in `tests/test_graph.py::test_grounding_system_prompt_is_verbatim`. Editing it requires an ADR. Same applies to `MAX_REWRITES` and `GROUNDING_THRESHOLD` — they're tested constants.

## /search endpoint

```bash
# Default: hybrid (BM25 + dense + RRF k=60) + cross-encoder rerank, top 5
curl -s -H 'X-API-Key: dev-local-key-change-me' \
  'http://localhost:8000/search?q=what+is+RRF' | jq

# Dense only (for ablation)
curl -s -H 'X-API-Key: dev-local-key-change-me' \
  'http://localhost:8000/search?q=foo&hybrid=false' | jq

# Hybrid without rerank (for ablation)
curl -s -H 'X-API-Key: dev-local-key-change-me' \
  'http://localhost:8000/search?q=foo&rerank=false' | jq

# Tune the candidate pool
curl -s -H 'X-API-Key: dev-local-key-change-me' \
  'http://localhost:8000/search?q=foo&fan_out=100&top_k=10' | jq
```

Response shape:

```json
{
  "query": "...",
  "stage": "hybrid+rerank",
  "count": 5,
  "results": [
    {"point_id": "...", "doc_id": "...", "chunk_index": 0, "text": "...",
     "title": "sample.txt", "source_uri": "...", "score": 0.92}
  ]
}
```

## Layout (target after milestone 7)

```
apps/api/src/
├── llm/                  # provider Protocol + anthropic/openai/ollama implementations (M7+)
│   ├── provider.py
│   ├── anthropic.py
│   ├── openai.py
│   └── ollama.py
├── ingestion/            # M3
│   ├── loaders.py
│   ├── chunker.py
│   ├── pipeline.py
│   └── cli.py
├── retrieval/            # M4–M6
│   ├── dense.py
│   ├── sparse.py         # BM25
│   ├── hybrid.py         # RRF fusion
│   └── rerank.py         # cross-encoder
├── graph/                # M7–M10
│   ├── state.py
│   ├── nodes.py
│   └── build.py
└── routes/
    ├── chat.py           # M8 — POST /chat (SSE)
    ├── ingest.py         # M3+M12 — POST /ingest
    └── health.py         # M2 ✅
```

## Commands

```bash
uv sync                                                       # install
uv run uvicorn src.main:app --reload                          # dev server
uv run python -m src.ingestion.cli ../../data/sample.txt      # ingest a document
uv run pytest                                                 # tests
uv run pytest -xvs tests/test_chunker.py                      # one test, verbose
uv run ruff check src/                                        # lint
uv run ruff format src/                                       # format
uv run mypy src/                                              # strict type-check
```

## Hard rules enforced here

The 11 MTCs from BRD-01 §3.7 — every condition has its grep target in `apps/api/src/` so the `security-auditor` subagent can verify them programmatically. Currently wired:

- **MTC-01** One collection per embedder: `src/config.py.qdrant_collection`
- **MTC-02** Idempotent upsert: `src/ingestion/chunker.py.point_id` (UUIDv5) + `pipeline.py` content_hash dedupe
- **MTC-03** Hybrid search: `src/retrieval/hybrid.py.hybrid_search` (dense + BM25 + RRF k=60)
- **MTC-04** Verbatim grounding system prompt: `src/graph/nodes.py.GENERATE_SYSTEM_PROMPT` + unit-tested
- **MTC-06** CORS allowlist: `src/main.py` `CORSMiddleware(allow_origins=settings.origins_list)`
- **MTC-07** API key dep: `src/security.py.require_api_key` — wired to `/search`, `/chat`, `/ingest`
- **MTC-08** Rate limit: `src/limits.py` shared `Limiter` + `@limiter.limit` on `/chat` (20/min) and `/ingest` (5/min)
- **MTC-05** DeepEval suite: `evals/{test_answer,test_retrieval,test_rerank}.py` + `.github/workflows/eval.yml` — **Phase 7a advisory** (`continue-on-error: true`). Becomes blocking in Phase 7b once the dataset hits 100-200 cases.
- **Observability**: `src/observability/langfuse.py:get_callback_handler()` + `src/routes/chat.py:_build_graph_config()` wire the Langfuse v3 LangChain `CallbackHandler` into every `graph.astream()` call. Per-node spans are automatic; per-LLM-call spans come from `@observe()` on provider methods. Traces are tagged with `langfuse_session_id`, `env`, and `llm_provider`.
- **MTC-09** Upload guards: `src/routes/ingest.py` — chunked size cap (25 MB), MIME allowlist + extension fallback, 60 s `asyncio.wait_for`, lru-cached `Semaphore(2)` for concurrency
- **MTC-10** `max_output_tokens=1024`: `src/llm/{anthropic,openai,ollama}.py` all clamp via `HARD_MAX_TOKENS`
- **MTC-11** `text-embedding-3-small` 1536d locked: `src/config.py.embedding_dimension` + `src/llm/openai.py.OpenAIEmbedder`

**All 11 MTCs are now in code.** MTC-05 is in advisory mode until the eval dataset expands to Phase 7b size.

## Reranker ablation (mandatory before M11 closes)

Per BRD-01 §7.2 BRD.01.3206 and plan.md §Milestone 6: the cross-encoder reranker
must show ≥ 10% NDCG@5 lift over fusion-only. Until the eval dataset exists
(M11), this is verified manually:

```bash
# baseline: hybrid only
curl -s -H 'X-API-Key: ...' 'http://localhost:8000/search?q=...&rerank=false' | jq .results

# with rerank
curl -s -H 'X-API-Key: ...' 'http://localhost:8000/search?q=...&rerank=true' | jq .results
```

The DeepEval `test_rerank.py` (M11) automates this ablation against the dataset
and feeds the result into the `rag-evaluator` subagent's verdict.
