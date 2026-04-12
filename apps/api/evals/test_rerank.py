"""Reranker ablation — proves the cross-encoder earns its latency cost.

Per BRD-01 §7.2 BRD.01.3206 and plan.md §Milestone 6: the cross-encoder reranker
must show a measurable lift in retrieval quality over fusion-only. If it doesn't,
the latency cost is unjustified and the reranker should be dropped or swapped
to a smaller model.

This test runs the same questions through `hybrid_search` (no rerank) and the
full `hybrid + rerank` chain, then compares ContextualPrecision scores from
DeepEval. If post-rerank precision is lower than pre-rerank precision, the
reranker is making things worse — that's an instant fail.
"""

import asyncio
from typing import Any

import pytest
from deepeval.metrics import ContextualPrecisionMetric
from deepeval.test_case import LLMTestCase

from src.retrieval.hybrid import hybrid_search
from src.retrieval.rerank import rerank as rerank_chunks

# A win is "post-rerank average ≥ pre-rerank average + 0.05" — modest, since
# our dataset is only 17 cases. Phase 7b will tighten this to ≥10% lift.
MIN_LIFT = 0.05


def _format_chunks(chunks: list) -> list[str]:
    return [
        f"[doc_id={c.doc_id} chunk={c.chunk_index}] {c.text[:240]}"
        for c in chunks
    ]


async def _retrieve_no_rerank(question: str) -> list:
    return (await hybrid_search(question, top_k=5))[:5]


async def _retrieve_with_rerank(question: str) -> list:
    candidates = await hybrid_search(question, top_k=50)
    return await rerank_chunks(question, candidates, top_k=5)


@pytest.fixture(scope="session")
def rerank_ablation(answerable_cases: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Score each answerable case twice — once without rerank, once with — and
    return the per-case ContextualPrecision scores."""
    metric_no_rerank: list[float] = []
    metric_with_rerank: list[float] = []
    case_ids: list[str] = []

    for case in answerable_cases:
        question = case["question"]
        no_rerank_chunks = asyncio.run(_retrieve_no_rerank(question))
        with_rerank_chunks = asyncio.run(_retrieve_with_rerank(question))

        if not no_rerank_chunks or not with_rerank_chunks:
            continue

        m1 = ContextualPrecisionMetric(threshold=0.0)
        m1.measure(
            LLMTestCase(
                input=question,
                actual_output=case["actual_answer"],
                expected_output=case.get("expected_answer", ""),
                retrieval_context=_format_chunks(no_rerank_chunks),
            )
        )
        metric_no_rerank.append(float(m1.score))

        m2 = ContextualPrecisionMetric(threshold=0.0)
        m2.measure(
            LLMTestCase(
                input=question,
                actual_output=case["actual_answer"],
                expected_output=case.get("expected_answer", ""),
                retrieval_context=_format_chunks(with_rerank_chunks),
            )
        )
        metric_with_rerank.append(float(m2.score))
        case_ids.append(case["id"])

    return {
        "case_ids": case_ids,
        "no_rerank": metric_no_rerank,
        "with_rerank": metric_with_rerank,
    }


def test_rerank_does_not_make_things_worse(rerank_ablation: dict[str, list[float]]) -> None:
    no = rerank_ablation["no_rerank"]
    yes = rerank_ablation["with_rerank"]
    if not no or not yes:
        pytest.skip("ablation produced no scores — pipeline broken")

    avg_no = sum(no) / len(no)
    avg_yes = sum(yes) / len(yes)
    assert avg_yes >= avg_no, (
        f"REGRESSION: post-rerank precision {avg_yes:.3f} < pre-rerank {avg_no:.3f}. "
        f"The reranker is hurting quality and should be dropped or swapped."
    )


def test_rerank_lift_meets_minimum(rerank_ablation: dict[str, list[float]]) -> None:
    """Phase 7a: advisory threshold of +0.05. Phase 7b: tighten to ≥10% lift."""
    no = rerank_ablation["no_rerank"]
    yes = rerank_ablation["with_rerank"]
    if not no or not yes:
        pytest.skip("ablation produced no scores — pipeline broken")

    avg_no = sum(no) / len(no)
    avg_yes = sum(yes) / len(yes)
    lift = avg_yes - avg_no
    assert lift >= MIN_LIFT, (
        f"Reranker lift {lift:+.3f} below minimum {MIN_LIFT}. "
        f"avg pre-rerank={avg_no:.3f} avg post-rerank={avg_yes:.3f}. "
        f"Either the reranker isn't earning its keep or the dataset is too small "
        f"to detect the difference (Phase 7a uses 17 cases — expand to 100-200 in 7b)."
    )
