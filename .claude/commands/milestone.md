---
description: Run the milestone-N exit checks from plan.md §Phase 11 and report PASS/FAIL with remediation.
argument-hint: [milestone_number 1-15]
allowed-tools: Bash, Read, Glob, Grep
---

Verify milestone $ARGUMENTS is actually complete per `plan.md` §Phase 11.

If $ARGUMENTS is not a number 1-15, fail with the list of milestones from plan.md.

## Per-milestone exit criteria

| # | Milestone | Exit checks |
|---|---|---|
| 1 | Repo scaffold + docker-compose up | `docker compose ps` shows qdrant + langfuse + postgres healthy; `curl localhost:6333/readyz` returns OK; `curl localhost:3001` returns 200 |
| 2 | FastAPI hello + /health + Langfuse init | `curl localhost:8000/health` returns `{"status":"ok"}`; backend log shows Langfuse client initialized |
| 3 | Ingestion pipeline (CLI) | `/ingest-test data/sample.pdf` passes including idempotency |
| 4 | Dense retrieval `/search?q=…` | `curl 'localhost:8000/search?q=test'` returns top-k chunks |
| 5 | BM25 + RRF fusion | `apps/api/src/retrieval/hybrid.py` exists; calls both dense + sparse; fuses via RRF |
| 6 | Cross-encoder rerank + p95 measurement | `apps/api/src/retrieval/rerank.py` exists; reranker ablation shows ≥10% NDCG@5 lift OR fallback documented |
| 7 | LangGraph skeleton (rewrite → retrieve → generate, no loop) | `apps/api/src/graph/build.py` exists; smoke test runs end-to-end |
| 8 | Streaming /chat SSE | `curl --no-buffer -H 'X-API-Key: ...' -X POST localhost:8000/chat …` shows token-by-token stream + final citations frame |
| 9 | Next.js chat UI | `cd apps/web && pnpm dev` runs; browser shows streamed answer + sources panel |
| 10 | Self-grading loop | Low-grounding question triggers exactly one rewrite (proven via Langfuse trace) |
| 11 | DeepEval baseline (Phase 7a — advisory) | `apps/api/evals/baselines/` has at least one snapshot; `/eval` runs without error |
| 12 | File upload UI → /ingest | Drag-drop in `/ingest` page produces upserts visible in Qdrant |
| 13 | Deploy: Railway + Vercel + Langfuse | Prod URLs for api, web, and Langfuse are reachable; prod /chat answers a known PDF question with citations |
| 14 | All ADRs written | `docs/adr/0001`–`0010` exist per plan §Phase 10 |
| 15 | /simplify + /review-pr passes | No actionable findings remaining |

## Workflow

1. Look up the row for milestone $ARGUMENTS.
2. Run each check in order. Stop on the first failure.
3. Report:
   ```
   ## Milestone $ARGUMENTS — {title}
   - Check 1: ✅ / ❌  (evidence)
   - Check 2: ...
   - Verdict: COMPLETE | INCOMPLETE — {remediation}
   ```
4. For COMPLETE: suggest committing with `feat: complete milestone N — {title}` (use the `/commit` skill).
5. For INCOMPLETE: list the smallest next action.
