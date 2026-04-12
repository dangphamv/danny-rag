# DeepEval suite — Phase 7a (advisory)

The eval harness for the RAG pipeline. Currently in **Phase 7a** per BRD-01 §7.2 BRD.01.3206 / plan.md §Phase 7:

- 17 hand-curated Q/A cases (10 extractive · 3 multi-hop · 4 out-of-scope refusals)
- Tests run end-to-end against the live graph (Qdrant + LLM provider + DeepEval judge)
- **Advisory only** — failures don't block merges. The CI workflow has `continue-on-error: true`.
- Phase 7b will expand to 100-200 cases and flip the gate to blocking (MTC-05).

## Files

```
evals/
├── dataset.jsonl         # 17 Q/A cases
├── conftest.py           # session-scoped fixture: runs every case through the graph once
├── test_answer.py        # Faithfulness, Hallucination, AnswerRelevancy + refusal contract
├── test_retrieval.py     # ContextualRelevancy
├── test_rerank.py        # Reranker ablation: post-rerank vs pre-rerank precision
└── baselines/            # JSON snapshots per commit (populated by future runs)
```

## Prerequisites

The suite is an integration test. It needs:

1. **Local data plane up**: `docker compose up -d`
2. **Sample doc ingested**: `cd apps/api && uv run python -m src.ingestion.cli ../../data/sample.txt`
3. **API keys in `.env`**:
   - `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) — used by the chat graph itself
   - `OPENAI_API_KEY` — used by DeepEval as the judge model

## Run it

```bash
cd apps/api

# Standard pytest invocation
uv run pytest evals/ -v

# DeepEval's wrapped runner with prettier reports
uv run deepeval test run evals/

# Just the answer-quality tests
uv run pytest evals/test_answer.py -v

# Just the rerank ablation
uv run pytest evals/test_rerank.py -v
```

## Thresholds

| Metric | Threshold | Source |
|---|---|---|
| Faithfulness | ≥ 0.85 | BRD-01 §2.3 |
| Hallucination | ≤ 0.10 | BRD-01 §2.3 |
| AnswerRelevancy | ≥ 0.70 | DeepEval default |
| ContextualRelevancy | ≥ 0.70 | DeepEval default |
| Reranker lift (Phase 7a) | ≥ +0.05 | conservative on small dataset |
| Reranker lift (Phase 7b) | ≥ 10% NDCG@5 | per BRD-01 §7.2 BRD.01.3206 |

## Phase 7a → 7b transition checklist

When the dataset reaches ~100 cases:

1. Drop `continue-on-error: true` from `.github/workflows/eval.yml` (the gate becomes blocking — MTC-05).
2. Replace fixed thresholds in `test_answer.py` with statistical floors (2σ over the trailing 7 baseline runs) — small samples have high variance.
3. Tighten `test_rerank.py` `MIN_LIFT` to a 10% relative NDCG@5 improvement and add `ContextualRecallMetric` once `dataset.jsonl` carries per-case `relevant_chunks` labels.
4. Bump dataset to include real out-of-scope adversarial cases (jailbreaks, irrelevant injections, contradictory context).

## Adding cases

Append a JSON line to `dataset.jsonl` with these fields:

| Field | Required | Notes |
|---|---|---|
| `id` | yes | unique, kebab-case |
| `category` | yes | `extractive` / `multi-hop` / `out-of-scope` |
| `question` | yes | the user query |
| `expected_answer` | for answerable cases | string the answer should contain or paraphrase |
| `expected_refusal` | for refusal cases | `true` |

After adding cases, run the suite locally and (if accepted) commit the dataset change as part of the PR that uses it.
