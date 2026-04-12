from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.graph.nodes import (
    generate,
    rerank_node,
    retrieve,
    rewrite_query,
    self_grade,
    should_retry,
)
from src.graph.state import GraphState


def _build_graph() -> StateGraph[GraphState, Any, GraphState, GraphState]:
    builder: StateGraph[GraphState, Any, GraphState, GraphState] = StateGraph(GraphState)

    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("retrieve", retrieve)
    builder.add_node("rerank", rerank_node)
    builder.add_node("generate", generate)
    builder.add_node("self_grade", self_grade)

    builder.add_edge(START, "rewrite_query")
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("retrieve", "rerank")
    builder.add_edge("rerank", "generate")
    builder.add_edge("generate", "self_grade")

    # M10: single self-grading loop. should_retry returns "retry" or "end".
    # The loop is bounded by `should_retry` checking `rewrite_count >= MAX_REWRITES`.
    builder.add_conditional_edges(
        "self_grade",
        should_retry,
        {
            "retry": "rewrite_query",
            "end": END,
        },
    )

    return builder


@lru_cache(maxsize=1)
def get_compiled_graph() -> Any:
    return _build_graph().compile()
