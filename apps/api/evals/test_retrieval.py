"""Retrieval-quality metrics — does the retrieved context cover the question?

Phase 7a: ContextualRelevancy only (no ground-truth labels needed). Phase 7b
will add ContextualRecall once the dataset includes per-case relevant_chunks.
"""

from typing import Any

import pytest
from deepeval.metrics import ContextualRelevancyMetric
from deepeval.test_case import LLMTestCase

CONTEXTUAL_RELEVANCY_THRESHOLD = 0.7


@pytest.mark.parametrize("case_idx", range(100))
def test_contextual_relevancy(
    answerable_cases: list[dict[str, Any]], case_idx: int
) -> None:
    if case_idx >= len(answerable_cases):
        pytest.skip(f"only {len(answerable_cases)} answerable cases")
    case = answerable_cases[case_idx]
    if case.get("error"):
        pytest.fail(f"{case['id']} pipeline error: {case['error']}")
    if not case["retrieval_context"]:
        pytest.fail(f"{case['id']} produced empty retrieval context — retrieval broken")

    metric = ContextualRelevancyMetric(threshold=CONTEXTUAL_RELEVANCY_THRESHOLD)
    test_case = LLMTestCase(
        input=case["question"],
        actual_output=case["actual_answer"],
        retrieval_context=case["retrieval_context"],
    )
    metric.measure(test_case)
    assert metric.score >= CONTEXTUAL_RELEVANCY_THRESHOLD, (
        f"{case['id']} contextual relevancy {metric.score:.3f} < "
        f"{CONTEXTUAL_RELEVANCY_THRESHOLD}: {metric.reason}"
    )
