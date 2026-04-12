"""Answer-quality metrics — Faithfulness + Hallucination + AnswerRelevancy.

Phase 7a (current): advisory only. Tests fail per-case but the GitHub Actions
workflow has `continue-on-error: true` so they don't block merges.

Phase 7b (after dataset expansion to 100-200 cases): remove `continue-on-error`,
making Faithfulness + Hallucination thresholds blocking CI gates per BRD-01
§3.7 MTC-05.
"""

from typing import Any

import pytest
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    HallucinationMetric,
)
from deepeval.test_case import LLMTestCase

from src.graph.nodes import REFUSAL_TEXT

# Thresholds are paired with BRD-01 §2.3 success metrics.
FAITHFULNESS_THRESHOLD = 0.85
HALLUCINATION_MAX = 0.10
ANSWER_RELEVANCY_THRESHOLD = 0.7


def _make_test_case(case: dict[str, Any]) -> LLMTestCase:
    return LLMTestCase(
        input=case["question"],
        actual_output=case["actual_answer"],
        retrieval_context=case["retrieval_context"],
        # `context` is the same as retrieval_context here — Hallucination metric
        # needs it to score whether the answer introduces information not present.
        context=case["retrieval_context"],
    )


@pytest.mark.parametrize("case_idx", range(100))
def test_faithfulness(answerable_cases: list[dict[str, Any]], case_idx: int) -> None:
    if case_idx >= len(answerable_cases):
        pytest.skip(f"only {len(answerable_cases)} answerable cases")
    case = answerable_cases[case_idx]
    if case.get("error"):
        pytest.fail(f"case {case['id']} failed to run: {case['error']}")
    if not case["retrieval_context"]:
        pytest.skip(f"case {case['id']} produced no retrieval context")

    metric = FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD)
    test_case = _make_test_case(case)
    metric.measure(test_case)
    assert metric.score >= FAITHFULNESS_THRESHOLD, (
        f"{case['id']} faithfulness {metric.score:.3f} < {FAITHFULNESS_THRESHOLD}: "
        f"{metric.reason}"
    )


@pytest.mark.parametrize("case_idx", range(100))
def test_hallucination(answerable_cases: list[dict[str, Any]], case_idx: int) -> None:
    if case_idx >= len(answerable_cases):
        pytest.skip(f"only {len(answerable_cases)} answerable cases")
    case = answerable_cases[case_idx]
    if case.get("error") or not case["retrieval_context"]:
        pytest.skip(f"case {case['id']} not runnable")

    metric = HallucinationMetric(threshold=HALLUCINATION_MAX)
    test_case = _make_test_case(case)
    metric.measure(test_case)
    # HallucinationMetric: lower is better. score is the hallucination rate.
    assert metric.score <= HALLUCINATION_MAX, (
        f"{case['id']} hallucination {metric.score:.3f} > {HALLUCINATION_MAX}: "
        f"{metric.reason}"
    )


@pytest.mark.parametrize("case_idx", range(100))
def test_answer_relevancy(
    answerable_cases: list[dict[str, Any]], case_idx: int
) -> None:
    if case_idx >= len(answerable_cases):
        pytest.skip(f"only {len(answerable_cases)} answerable cases")
    case = answerable_cases[case_idx]
    if case.get("error") or not case["retrieval_context"]:
        pytest.skip(f"case {case['id']} not runnable")

    metric = AnswerRelevancyMetric(threshold=ANSWER_RELEVANCY_THRESHOLD)
    test_case = _make_test_case(case)
    metric.measure(test_case)
    assert metric.score >= ANSWER_RELEVANCY_THRESHOLD, (
        f"{case['id']} relevancy {metric.score:.3f} < {ANSWER_RELEVANCY_THRESHOLD}: "
        f"{metric.reason}"
    )


def test_refusals_match_grounding_contract(refusal_cases: list[dict[str, Any]]) -> None:
    """MTC-04 — out-of-scope questions MUST produce the verbatim refusal."""
    failures: list[str] = []
    for case in refusal_cases:
        if case.get("error"):
            failures.append(f"{case['id']}: error: {case['error']}")
            continue
        if REFUSAL_TEXT not in case["actual_answer"]:
            failures.append(
                f"{case['id']}: expected refusal containing {REFUSAL_TEXT!r}, "
                f"got {case['actual_answer'][:120]!r}"
            )
    assert not failures, "Grounding contract violations:\n" + "\n".join(failures)
