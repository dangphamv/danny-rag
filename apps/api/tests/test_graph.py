"""Smoke test the LangGraph topology with mocked LLM + retrieval.

These tests verify the graph wiring (nodes, edges, state passing, custom
stream events, self-grading loop) without hitting OpenAI / Anthropic / Qdrant.
"""

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from src.graph.build import _build_graph
from src.graph.nodes import (
    GENERATE_SYSTEM_PROMPT,
    GROUNDING_THRESHOLD,
    MAX_REWRITES,
    REFUSAL_TEXT,
    should_retry,
)
from src.llm.protocol import Message
from src.retrieval.types import ScoredChunk


class FakeLLM:
    """Stub LLM for unit tests.

    Detects whether a `generate()` call is a rewrite, a grade, or something
    else by sniffing the system prompt. The grade response can be sequenced
    via `grade_scores=[...]` so loop tests can flip the second grade to high.
    """

    def __init__(
        self,
        *,
        generate_text: str = "rewritten query",
        stream_tokens: list[str] | None = None,
        grade_scores: list[float] | None = None,
    ) -> None:
        self._generate_text = generate_text
        self._stream_tokens = stream_tokens or ["Hello", " ", "world", "."]
        self._grade_scores = list(grade_scores) if grade_scores is not None else None
        self._grade_call_index = 0
        self.calls: list[list[Message]] = []
        self.rewrite_calls = 0
        self.grade_calls = 0

    @property
    def model_name(self) -> str:
        return "fake"

    async def generate(self, messages: list[Message], max_tokens: int = 1024) -> str:
        self.calls.append(messages)
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        if "grader of answer grounding" in system:
            self.grade_calls += 1
            if self._grade_scores is not None:
                idx = min(self._grade_call_index, len(self._grade_scores) - 1)
                self._grade_call_index += 1
                return str(self._grade_scores[idx])
            return "1.0"  # default: high score → no retry
        if "search query rewriter" in system:
            self.rewrite_calls += 1
        return self._generate_text

    async def astream(self, messages: list[Message], max_tokens: int = 1024) -> AsyncIterator[str]:
        self.calls.append(messages)
        for tok in self._stream_tokens:
            yield tok


def fake_chunk(point_id: str = "p1", text: str = "fake doc text") -> ScoredChunk:
    return ScoredChunk(
        point_id=point_id,
        doc_id="docA",
        chunk_index=0,
        text=text,
        title="fake.txt",
        source_uri="/tmp/fake.txt",
        score=0.9,
    )


# ---------- prompt + constant invariants ----------


def test_grounding_system_prompt_is_verbatim() -> None:
    """MTC-04 — never mutate this string without an ADR."""
    expected = (
        "Answer only from the provided context. Cite source chunks by `doc_id`. "
        "If the context is insufficient, reply `I don't have enough information to answer that` "
        "and stop. Do not use prior knowledge."
    )
    assert GENERATE_SYSTEM_PROMPT == expected


def test_grounding_threshold_is_07() -> None:
    assert GROUNDING_THRESHOLD == 0.7


def test_max_rewrites_caps_at_initial_plus_one() -> None:
    # Per BRD-01 §7.2 BRD.01.3206 / plan.md §4.3 — single retry only.
    assert MAX_REWRITES == 2


# ---------- should_retry routing (pure function) ----------


def test_should_retry_high_score_ends() -> None:
    assert should_retry({"grounding_score": 0.9, "rewrite_count": 1}) == "end"


def test_should_retry_at_threshold_ends() -> None:
    assert should_retry({"grounding_score": GROUNDING_THRESHOLD, "rewrite_count": 1}) == "end"


def test_should_retry_low_score_below_max_retries() -> None:
    assert should_retry({"grounding_score": 0.3, "rewrite_count": 1}) == "retry"


def test_should_retry_low_score_at_max_ends() -> None:
    assert should_retry({"grounding_score": 0.0, "rewrite_count": MAX_REWRITES}) == "end"


def test_should_retry_missing_score_ends() -> None:
    assert should_retry({"rewrite_count": 0}) == "end"


# ---------- end-to-end graph behavior ----------


@pytest.mark.asyncio
async def test_graph_streams_tokens_and_citations() -> None:
    fake_llm = FakeLLM(stream_tokens=["Hello", " ", "from", " ", "the", " ", "fake", " ", "LLM", "."])

    async def fake_hybrid(query: str, top_k: int = 50) -> list[ScoredChunk]:
        return [fake_chunk("p1"), fake_chunk("p2", "second chunk")]

    async def fake_rerank(query: str, chunks: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        return chunks

    with (
        patch("src.graph.nodes.get_llm", return_value=fake_llm),
        patch("src.graph.nodes.hybrid_search", side_effect=fake_hybrid),
        patch("src.graph.nodes.rerank_chunks", side_effect=fake_rerank),
    ):
        graph = _build_graph().compile()
        events: list[dict] = []
        async for event in graph.astream(
            {"question": "what is fake?", "session_id": "s1", "rewrite_count": 0},
            stream_mode="custom",
        ):
            events.append(event)

    token_events = [e for e in events if e["type"] == "token"]
    citation_events = [e for e in events if e["type"] == "citations"]
    grade_events = [e for e in events if e["type"] == "grade"]

    assert len(token_events) == 10
    assert "".join(e["content"] for e in token_events) == "Hello from the fake LLM."
    assert len(citation_events) == 1
    assert len(citation_events[0]["citations"]) == 2
    assert len(grade_events) == 1  # default fake grade is 1.0 → no retry
    assert grade_events[0]["score"] == 1.0


@pytest.mark.asyncio
async def test_graph_refuses_when_no_context() -> None:
    fake_llm = FakeLLM()

    async def empty_hybrid(query: str, top_k: int = 50) -> list[ScoredChunk]:
        return []

    async def passthrough_rerank(query: str, chunks: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        return chunks

    with (
        patch("src.graph.nodes.get_llm", return_value=fake_llm),
        patch("src.graph.nodes.hybrid_search", side_effect=empty_hybrid),
        patch("src.graph.nodes.rerank_chunks", side_effect=passthrough_rerank),
    ):
        graph = _build_graph().compile()
        events: list[dict] = []
        async for event in graph.astream(
            {"question": "what is fake?", "session_id": "s1", "rewrite_count": 0},
            stream_mode="custom",
        ):
            events.append(event)

    token_events = [e for e in events if e["type"] == "token"]
    citation_events = [e for e in events if e["type"] == "citations"]
    grade_events = [e for e in events if e["type"] == "grade"]

    # MTC-04: refuse when context is insufficient. Do NOT use prior knowledge.
    assert len(token_events) == 1
    assert token_events[0]["content"] == REFUSAL_TEXT
    assert citation_events[0]["citations"] == []
    # self_grade should skip the LLM call entirely on a refusal answer.
    assert len(grade_events) == 1
    assert grade_events[0]["skipped"] is True
    assert fake_llm.grade_calls == 0


@pytest.mark.asyncio
async def test_graph_uses_rewritten_question_for_retrieval() -> None:
    fake_llm = FakeLLM(generate_text="REWRITTEN: what is fake")
    captured_queries: list[str] = []

    async def capturing_hybrid(query: str, top_k: int = 50) -> list[ScoredChunk]:
        captured_queries.append(query)
        return [fake_chunk()]

    async def passthrough_rerank(query: str, chunks: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        return chunks

    with (
        patch("src.graph.nodes.get_llm", return_value=fake_llm),
        patch("src.graph.nodes.hybrid_search", side_effect=capturing_hybrid),
        patch("src.graph.nodes.rerank_chunks", side_effect=passthrough_rerank),
    ):
        graph = _build_graph().compile()
        async for _ in graph.astream(
            {"question": "what is fake?", "session_id": "s1", "rewrite_count": 0},
            stream_mode="custom",
        ):
            pass

    assert captured_queries == ["REWRITTEN: what is fake"]


# ---------- M10: self-grading loop end-to-end ----------


@pytest.mark.asyncio
async def test_loop_fires_on_low_score() -> None:
    # First grade low (0.3), second high (0.9). Expect exactly 2 rewrites + 2 grades.
    fake_llm = FakeLLM(grade_scores=[0.3, 0.9])

    async def fake_hybrid(query: str, top_k: int = 50) -> list[ScoredChunk]:
        return [fake_chunk()]

    async def passthrough_rerank(query: str, chunks: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        return chunks

    with (
        patch("src.graph.nodes.get_llm", return_value=fake_llm),
        patch("src.graph.nodes.hybrid_search", side_effect=fake_hybrid),
        patch("src.graph.nodes.rerank_chunks", side_effect=passthrough_rerank),
    ):
        graph = _build_graph().compile()
        events: list[dict] = []
        async for event in graph.astream(
            {"question": "what is fake?", "session_id": "s1", "rewrite_count": 0},
            stream_mode="custom",
        ):
            events.append(event)

    grade_events = [e for e in events if e["type"] == "grade"]
    retry_events = [e for e in events if e["type"] == "retry"]

    assert len(grade_events) == 2
    assert grade_events[0]["score"] == 0.3
    assert grade_events[1]["score"] == 0.9
    assert len(retry_events) == 1  # one retry event emitted on the second rewrite
    assert retry_events[0]["rewrite_count"] == 2
    assert fake_llm.rewrite_calls == 2


@pytest.mark.asyncio
async def test_loop_terminates_after_max_rewrites_when_score_stays_low() -> None:
    # All grades return 0.0. Loop must still terminate after MAX_REWRITES rewrites.
    fake_llm = FakeLLM(grade_scores=[0.0, 0.0, 0.0, 0.0])

    async def fake_hybrid(query: str, top_k: int = 50) -> list[ScoredChunk]:
        return [fake_chunk()]

    async def passthrough_rerank(query: str, chunks: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        return chunks

    with (
        patch("src.graph.nodes.get_llm", return_value=fake_llm),
        patch("src.graph.nodes.hybrid_search", side_effect=fake_hybrid),
        patch("src.graph.nodes.rerank_chunks", side_effect=passthrough_rerank),
    ):
        graph = _build_graph().compile()
        async for _ in graph.astream(
            {"question": "what is fake?", "session_id": "s1", "rewrite_count": 0},
            stream_mode="custom",
        ):
            pass

    assert fake_llm.rewrite_calls == MAX_REWRITES
    assert fake_llm.grade_calls == MAX_REWRITES


@pytest.mark.asyncio
async def test_loop_does_not_fire_on_high_score() -> None:
    fake_llm = FakeLLM(grade_scores=[0.95])

    async def fake_hybrid(query: str, top_k: int = 50) -> list[ScoredChunk]:
        return [fake_chunk()]

    async def passthrough_rerank(query: str, chunks: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        return chunks

    with (
        patch("src.graph.nodes.get_llm", return_value=fake_llm),
        patch("src.graph.nodes.hybrid_search", side_effect=fake_hybrid),
        patch("src.graph.nodes.rerank_chunks", side_effect=passthrough_rerank),
    ):
        graph = _build_graph().compile()
        events: list[dict] = []
        async for event in graph.astream(
            {"question": "what is fake?", "session_id": "s1", "rewrite_count": 0},
            stream_mode="custom",
        ):
            events.append(event)

    retry_events = [e for e in events if e["type"] == "retry"]
    assert len(retry_events) == 0
    assert fake_llm.rewrite_calls == 1
    assert fake_llm.grade_calls == 1
