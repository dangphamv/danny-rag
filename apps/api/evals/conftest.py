"""Shared pytest fixtures for the eval suite.

The `eval_cases` fixture is the expensive one — it runs the entire chat graph
end-to-end against every dataset case once and caches the results for the
session. Tests then assert against those cached results.

These tests REQUIRE running services:
  - Qdrant (with sample.txt ingested)
  - LLM provider keys (ANTHROPIC_API_KEY or OPENAI_API_KEY)
  - DeepEval judge keys (OPENAI_API_KEY by default)

Run with:  uv run pytest evals/ -v
   or:     uv run deepeval test run evals/
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from src.graph.build import get_compiled_graph

log = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).parent / "dataset.jsonl"


def load_dataset() -> list[dict[str, Any]]:
    with DATASET_PATH.open() as f:
        return [json.loads(line) for line in f if line.strip()]


async def _run_graph_once(question: str) -> tuple[str, list[dict[str, Any]]]:
    graph = get_compiled_graph()
    answer = ""
    citations: list[dict[str, Any]] = []
    async for event in graph.astream(
        {"question": question, "session_id": "eval", "rewrite_count": 0},
        stream_mode="custom",
    ):
        kind = event.get("type")
        if kind == "token":
            answer += event["content"]
        elif kind == "citations":
            citations = event["citations"]
        elif kind == "retry":
            # Self-grading loop fired — discard the previous answer.
            answer = ""
            citations = []
    return answer, citations


def _format_context(citations: list[dict[str, Any]]) -> list[str]:
    return [
        f"[doc_id={c['doc_id']} chunk={c['chunk_index']}] {c['snippet']}"
        for c in citations
    ]


@pytest.fixture(scope="session")
def eval_cases() -> list[dict[str, Any]]:
    """Run the chat graph against every dataset case. Session-scoped cache."""
    cases = load_dataset()
    log.info("eval fixture: running %d cases through the graph", len(cases))
    enriched: list[dict[str, Any]] = []
    for case in cases:
        try:
            answer, citations = asyncio.run(_run_graph_once(case["question"]))
        except Exception as exc:
            log.exception("eval case %s failed to run", case["id"])
            enriched.append({**case, "actual_answer": "", "retrieval_context": [], "error": str(exc)})
            continue
        enriched.append(
            {
                **case,
                "actual_answer": answer,
                "retrieval_context": _format_context(citations),
                "raw_citations": citations,
            }
        )
    return enriched


@pytest.fixture(scope="session")
def answerable_cases(eval_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in eval_cases if not c.get("expected_refusal")]


@pytest.fixture(scope="session")
def refusal_cases(eval_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in eval_cases if c.get("expected_refusal")]
