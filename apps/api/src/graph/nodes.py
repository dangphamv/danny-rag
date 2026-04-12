import logging
from typing import Any

from langgraph.types import StreamWriter

from src.config import get_settings
from src.graph.state import Citation, GraphState
from src.llm.factory import get_llm
from src.llm.protocol import Message
from src.retrieval.hybrid import hybrid_search
from src.retrieval.rerank import rerank as rerank_chunks
from src.retrieval.types import ScoredChunk

log = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "You are a search query rewriter. Take the user's question and rewrite it as a "
    "single, self-contained search query optimized for keyword and semantic retrieval. "
    "Strip filler words. Keep all proper nouns, technical terms, and numbers verbatim. "
    "Return only the rewritten query, no explanation, no quotes."
)

REWRITE_RETRY_SYSTEM_PROMPT = (
    "You are a search query rewriter. Your previous rewrite produced an answer that "
    "was poorly grounded in the retrieved context. Try a DIFFERENT phrasing — emphasize "
    "different keywords, expand acronyms, or be more specific. Return only the new "
    "query, no explanation, no quotes."
)

# MTC-04: this prompt is BINDING. Verbatim from BRD-01 §3.7. Do not edit.
GENERATE_SYSTEM_PROMPT = (
    "Answer only from the provided context. Cite source chunks by `doc_id`. "
    "If the context is insufficient, reply `I don't have enough information to answer that` "
    "and stop. Do not use prior knowledge."
)

GRADE_SYSTEM_PROMPT = (
    "You are a strict grader of answer grounding. Given a question, retrieved context, "
    "and a candidate answer, score how well the answer is grounded in the context.\n\n"
    "Scoring scale:\n"
    "  1.0 = every claim in the answer is directly supported by the context\n"
    "  0.7 = most claims supported, minor unsupported detail\n"
    "  0.3 = several claims unsupported or contradicting the context\n"
    "  0.0 = answer relies on information not present in the context\n\n"
    "Reply with ONLY a single floating-point number between 0.0 and 1.0. "
    "No explanation, no surrounding text."
)

REFUSAL_TEXT = "I don't have enough information to answer that"

SNIPPET_LENGTH = 240

# Grounding score below this triggers one rewrite-and-retry. Per BRD-01 §7.2 BRD.01.3206
# the loop is capped at one retry total — this threshold is paired with the rewrite_count
# guard in `should_retry` below.
GROUNDING_THRESHOLD = 0.7
MAX_REWRITES = 2  # initial + 1 retry


def _build_context(reranked: list[ScoredChunk]) -> str:
    return "\n\n".join(
        f"[doc_id={c.doc_id} chunk={c.chunk_index}] {c.text}" for c in reranked
    )


def _to_citation(chunk: ScoredChunk) -> Citation:
    snippet = chunk.text if len(chunk.text) <= SNIPPET_LENGTH else chunk.text[:SNIPPET_LENGTH] + "..."
    return Citation(
        doc_id=chunk.doc_id,
        chunk_index=chunk.chunk_index,
        title=chunk.title,
        source_uri=chunk.source_uri,
        page=chunk.page,
        snippet=snippet,
        score=chunk.score,
    )


async def rewrite_query(state: GraphState, writer: StreamWriter) -> dict[str, Any]:
    """Rewrite the user question into a search-optimized query.

    Increments `rewrite_count` so the self-grading loop guard can detect retries.
    On retries (count > 0) emits a `retry` event so the UI can reset the assistant
    message and show a re-rephrasing indicator.
    """
    count = state.get("rewrite_count", 0)
    is_retry = count > 0
    if is_retry:
        writer({"type": "retry", "rewrite_count": count + 1})

    question = state["question"]
    log.info("rewrite_query question=%r is_retry=%s", question, is_retry)
    system_prompt = REWRITE_RETRY_SYSTEM_PROMPT if is_retry else REWRITE_SYSTEM_PROMPT
    llm = get_llm()
    rewritten = await llm.generate(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        max_tokens=128,
    )
    cleaned = rewritten.strip().strip('"').strip("'") or question
    log.info("rewrite_query result=%r count=%d", cleaned, count + 1)
    return {"rewritten_question": cleaned, "rewrite_count": count + 1}


async def retrieve(state: GraphState) -> dict[str, Any]:
    query = state.get("rewritten_question") or state["question"]
    candidates = await hybrid_search(query, top_k=50)
    log.info("retrieve fetched=%d", len(candidates))
    return {"candidates": candidates}


async def rerank_node(state: GraphState) -> dict[str, Any]:
    candidates = state.get("candidates", [])
    if not candidates:
        return {"reranked": []}
    query = state.get("rewritten_question") or state["question"]
    reranked = await rerank_chunks(query, candidates, top_k=5)
    log.info("rerank kept=%d", len(reranked))
    return {"reranked": reranked}


async def generate(state: GraphState, writer: StreamWriter) -> dict[str, Any]:
    """Streaming generate node — see M8 for the protocol."""
    settings = get_settings()
    reranked = state.get("reranked", [])

    if not reranked:
        # MTC-04: insufficient context → refuse, do NOT use prior knowledge.
        writer({"type": "token", "content": REFUSAL_TEXT})
        writer({"type": "citations", "citations": []})
        return {"answer": REFUSAL_TEXT, "citations": []}

    context = _build_context(reranked)
    user_prompt = f"Context:\n{context}\n\nQuestion: {state['question']}"
    messages: list[Message] = [
        {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    llm = get_llm()
    full_answer = ""
    async for token in llm.astream(messages=messages, max_tokens=settings.max_output_tokens):
        writer({"type": "token", "content": token})
        full_answer += token

    citations = [_to_citation(c) for c in reranked]
    writer({"type": "citations", "citations": [c.model_dump() for c in citations]})
    log.info("generate done answer_len=%d citations=%d", len(full_answer), len(citations))
    return {"answer": full_answer, "citations": citations}


async def self_grade(state: GraphState, writer: StreamWriter) -> dict[str, Any]:
    """Score the answer's grounding in the retrieved context.

    Emits a `grade` event with the score so the UI / Langfuse can see why the
    loop fired (or didn't). Returns the score on the state for `should_retry`
    to read.
    """
    answer = state.get("answer", "")
    reranked = state.get("reranked", [])
    count = state.get("rewrite_count", 0)

    # Trivial cases — don't waste an LLM call.
    if not answer or not reranked or answer.strip() == REFUSAL_TEXT:
        writer({"type": "grade", "score": 1.0, "rewrite_count": count, "skipped": True})
        return {"grounding_score": 1.0}

    context = _build_context(reranked)
    grade_user_prompt = (
        f"Question: {state['question']}\n\n"
        f"Context:\n{context}\n\n"
        f"Answer: {answer}\n\n"
        "Score (0.0 to 1.0):"
    )
    llm = get_llm()
    raw = await llm.generate(
        messages=[
            {"role": "system", "content": GRADE_SYSTEM_PROMPT},
            {"role": "user", "content": grade_user_prompt},
        ],
        max_tokens=8,
    )
    try:
        score = float(raw.strip().split()[0])
        score = max(0.0, min(1.0, score))
    except (ValueError, IndexError):
        log.warning("self_grade returned non-numeric: %r — defaulting to 1.0 (no retry)", raw)
        score = 1.0

    log.info("self_grade score=%.3f rewrite_count=%d", score, count)
    writer({"type": "grade", "score": score, "rewrite_count": count, "skipped": False})
    return {"grounding_score": score}


def should_retry(state: GraphState) -> str:
    """Conditional edge: return 'retry' to loop back to rewrite_query, else 'end'."""
    score = state.get("grounding_score")
    count = state.get("rewrite_count", 0)
    if score is None or score >= GROUNDING_THRESHOLD:
        return "end"
    if count >= MAX_REWRITES:
        return "end"
    return "retry"
