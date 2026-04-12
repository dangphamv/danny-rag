# 0007. DeepEval for offline retrieval and answer-quality evaluation

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3206 (AI/ML), MTC-05

## Context

Retrieval changes are easy to break silently. A reranker swap, a chunk-size tweak, a system-prompt edit — any of those can drop grounding quality without producing any error. "Vibes-only" testing (manually asking questions and reading the answers) catches obvious regressions but misses subtle ones, and doesn't scale beyond a handful of queries.

The BRD's MTC-05 requires that **Faithfulness** and **Hallucination** become **blocking CI gates** so that any retrieval-touching PR has to prove it doesn't make things worse. The eval suite is the safety net — without it, the BRD's "all retrieval changes must ship with a regression run" rule has no teeth.

## Decision

Use **DeepEval** as the offline eval framework. Three test files in `apps/api/evals/`:

| File | Metrics | Source threshold |
|---|---|---|
| `test_answer.py` | `FaithfulnessMetric` (≥0.85), `HallucinationMetric` (≤0.10), `AnswerRelevancyMetric` (≥0.7) + a custom refusal-contract test | BRD §2.3 |
| `test_retrieval.py` | `ContextualRelevancyMetric` (≥0.7) | DeepEval default |
| `test_rerank.py` | `ContextualPrecisionMetric` ablation: rerank-on vs rerank-off, asserting positive lift | BRD.01.3206 |

A session-scoped pytest fixture (`evals/conftest.py:eval_cases`) runs every dataset case through the live graph **once** and caches `(answer, citations)`. Tests assert against the cached results, so each metric is one LLM judge call rather than one full pipeline run.

The eval suite is wired into a **GitHub Actions workflow** (`.github/workflows/eval.yml`) that runs nightly + on PRs touching retrieval/graph/llm/ingestion paths. The workflow uses `continue-on-error: true` for **Phase 7a** (advisory) — Phase 7b drops that flag and the suite becomes blocking per MTC-05.

The transition gate is documented in `apps/api/evals/README.md`.

## Rationale

- **LLM-as-judge metrics** are the only practical way to score open-ended answer quality at this scale. Ground-truth labeling for 100+ Q/A pairs is prohibitive; LLM-as-judge gets ~85% of the value at ~5% of the cost.
- **Faithfulness + Hallucination map directly to BRD §2.3 success metrics** — no translation layer between requirements and tests.
- **DeepEval is pytest-native**: same test runner as the rest of the project, no separate harness to learn or maintain.
- **Phase 7a (advisory) → Phase 7b (blocking) ramp** is a safe rollout. Small datasets (17 cases now, 100+ in 7b) have high variance — making them blocking too early produces false-positive regressions and erodes trust in the gate.
- **Session-scoped fixture** is the cost optimization that makes nightly runs cheap. ~17 graph runs once + ~80 metric judge calls ≈ pennies per run.

## Consequences

### Positive
- Retrieval regressions get caught automatically, not by users
- The grounding contract (MTC-04) is empirically verified, not just hoped-for
- The reranker ablation (`test_rerank.py`) provides ongoing justification for the latency cost — if rerank ever stops earning its keep, the test fails
- The `rag-evaluator` subagent in `.claude/agents/` automates running the suite and producing verdicts

### Negative
- **Tests cost real money** — pennies per run, but not free
- **Tests are slow** — ~10s per case, ~3-5 min full run
- **Tests require running services** — Qdrant + sample.txt ingested + API keys. Integration tests, not unit tests
- **LLM judges are non-deterministic** — same inputs can produce different scores between runs. Phase 7b's statistical-floor approach (2σ over trailing 7 runs) handles this; Phase 7a uses fixed thresholds because we don't have enough runs yet to compute 2σ
- **Dataset authoring is hand work** — 17 cases written manually for Phase 7a; expanding to 100+ is the M11 → Phase 7b project

### Neutral / Follow-ups
- Phase 7b adds `ContextualRecallMetric` once dataset cases carry per-case `relevant_chunks` ground-truth labels
- Phase 7b adds adversarial cases (jailbreak attempts, irrelevant context injection, contradictory chunks)
- Baseline snapshots in `apps/api/evals/baselines/` are populated by the `rag-evaluator` subagent on its first successful run (`.claude/agents/rag-evaluator.md` describes the baseline-update workflow)
- The `/eval` slash command invokes the `rag-evaluator` subagent — wired but not used until session restart

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **DeepEval** | LLM-as-judge native, pytest integration, Faithfulness/Hallucination metrics map to BRD | Costs money, slow, judge non-determinism | **Selected** — closest fit to BRD requirements |
| Ragas | Similar approach, also LLM-as-judge | Less mature ecosystem, fewer pre-built metrics, less pytest integration | Rejected — DeepEval is the more polished pytest experience |
| LangSmith eval | Tight LangChain integration | Vendor lock (see ADR-0009), hosted-only judge | Rejected — see ADR-0009 |
| Custom string-match metrics | Free, fast, deterministic | Can't score answer quality, can't detect paraphrase regressions | Rejected — would only catch the most obvious failures |
| No offline evals | No infrastructure to maintain | The whole BRD safety net falls apart | Rejected — defeats MTC-05 |
| Hand evaluation only | Highest fidelity per case | Doesn't scale; not reproducible | Rejected — works for spot checks, not as a CI gate |

## References

- [BRD-01 §3.7 MTC-05](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — DeepEval as blocking gate (Phase 7b)
- [BRD-01 §7.2 BRD.01.3206](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — AI/ML topic
- [BRD-01 §2.3](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — Faithfulness ≥0.85, Hallucination ≤0.10 targets
- `plan.md` §Phase 7a/7b — staged rollout
- `apps/api/evals/README.md` — runtime instructions, threshold table, transition checklist
- `apps/api/evals/test_*.py` — implementations
- `.github/workflows/eval.yml` — CI integration with the Phase 7a/7b switch
- ADR-0004 — reranker ablation that this suite enforces
- ADR-0009 — Langfuse over LangSmith (related vendor decision)
