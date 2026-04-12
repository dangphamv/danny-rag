---
description: Run the DeepEval suite via the rag-evaluator subagent and report metric deltas vs the latest baseline.
argument-hint: [optional: test_file_or_metric_filter]
allowed-tools: Bash(cd apps/api && uv run deepeval *), Read, Glob
---

Delegate this task to the `rag-evaluator` subagent.

If `$ARGUMENTS` is non-empty, treat it as a filter (e.g., `test_retrieval.py`, `test_answer.py`, or a `-k` keyword) and pass it to DeepEval. Otherwise run the full suite.

Required output from the subagent:
1. **Verdict** (PASS / ADVISORY / BLOCKING REGRESSION) on the first line
2. Per-metric delta table (baseline vs current)
3. Top 3 failing test cases if any
4. Recommendation: merge / fix-and-rerun / open-regression-issue

Do NOT update the baseline without explicit user approval.
