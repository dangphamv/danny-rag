# 0005. LangGraph over plain LangChain chains for graph orchestration

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3203 (Integration), BRD.01.3207 (Technology Selection)

## Context

The RAG pipeline is not a straight line. It has:

- Multiple sequential stages (rewrite, retrieve, rerank, generate)
- Per-stage state that flows downstream (`question` → `rewritten_question` → `candidates` → `reranked` → `answer`)
- A **conditional retry loop**: if `self_grade` decides the answer is poorly grounded, the pipeline rewrites the query and re-runs once (BRD §3.7 MTC, plan §4.3)
- Token streaming from inside the `generate` step that needs to surface as SSE to the browser
- Future need for session resumability via a Postgres checkpointer

LangChain's Expression Language (LCEL) `|` chains handle linear flows beautifully but don't natively express state-machine semantics, conditional routing, or loops. Trying to bolt those onto LCEL produces fragile glue code.

## Decision

Use **LangGraph** with a `StateGraph` keyed on a `TypedDict` `GraphState`. Each node is an `async def` function that returns a state-update dict. Conditional edges via `add_conditional_edges`. Token streaming via the **custom stream writer** pattern (`writer: StreamWriter` parameter on streaming nodes).

The compiled graph is cached behind `@lru_cache(maxsize=1) get_compiled_graph()`. The `/chat` route consumes it via `graph.astream(stream_mode="custom")`.

The single-retry loop is enforced by `should_retry()` checking `state["rewrite_count"] < MAX_REWRITES (=2)` — guaranteed termination, never an infinite loop.

## Rationale

- **State machine semantics match the problem**: nodes, edges, conditional routing, and a guarded loop are exactly what RAG-with-self-grading needs. LangGraph is the right shape.
- **Custom stream writer** is the bridge between graph orchestration and SSE token streaming. Tokens emitted from `generate` via `writer({"type": "token", ...})` flow through `astream(stream_mode="custom")` to the SSE response. Self-grading retries can use the same writer to emit `{"type": "retry"}` markers.
- **Postgres checkpointer** (`langgraph-checkpoint-postgres`) is wired-in-the-stack but not yet used — when session resumability becomes valuable, it's one config change. Other orchestration frameworks would require swapping this back in.
- **Single-loop guarantee** via `rewrite_count` is testable as a pure function (`tests/test_graph.py::test_should_retry_*`). Multi-loop graphs are easy to break; capping at 1 retry by construction is the right move for v1.
- **LangChain ecosystem alignment**: even though we don't use LangChain ChatModels directly (we have our own `LLMProvider` Protocol — see ADR-0006), LangGraph's design vocabulary matches LangChain. Future contributors will recognize the patterns.

## Consequences

### Positive
- The pipeline topology is one diagram (`build.py`), not a tangled control flow
- Adding/removing/reordering nodes is mechanical
- The self-grading loop is one conditional edge — easy to reason about
- Streaming tokens through nodes is first-class via the custom writer
- Tests can mock individual nodes via `unittest.mock.patch` and run the graph end-to-end

### Negative
- **LangGraph dep is not small** — pulls in significant LangChain ecosystem code
- **Custom stream writer is a relatively new LangGraph feature** (~2025) — pin the version, watch for API churn
- **Boilerplate** vs plain async functions for trivial linear flows
- **Learning curve**: future contributors need to know LangGraph mental model

### Neutral / Follow-ups
- The Postgres checkpointer is wired as a dep but not yet hooked into `get_compiled_graph()`. Activating it = passing `checkpointer=PostgresSaver(...)` to `.compile()`. Future ADR when sessions need to survive process restarts.
- Token streaming inside the generate node (writer-based) is documented in `apps/api/README.md`. If LangGraph ever ships a cleaner streaming primitive, revisit.
- Self-grading loop's `MAX_REWRITES = 2` and `GROUNDING_THRESHOLD = 0.7` are tested constants. Any change requires a new ADR per CLAUDE.md rule.

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **LangGraph StateGraph** | State machine native, conditional edges, checkpointer support, custom stream writer | Heavy dep, API churn risk | **Selected** — matches the problem shape |
| Plain async Python functions | Zero deps, full control | Lose checkpointer, lose orchestration observability hooks, hand-roll the loop guard | Rejected — reinventing LangGraph |
| LangChain LCEL `|` pipes | Idiomatic for linear chains | No native loop support, conditional routing is awkward | Rejected — wrong shape for the self-grading loop |
| Custom state machine class | Full control, learning value | Maintenance burden, no observability story, no checkpointer | Rejected — wheel-reinvention without payoff |
| Temporal / Airflow / Prefect | Industrial-grade orchestration | Massive overkill for in-process LLM flows | Rejected — wrong tool class entirely |

## References

- [BRD-01 §7.2 BRD.01.3206](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — pipeline topology requirement
- `plan.md` §4.3 — node sequence specification
- `apps/api/src/graph/build.py` — graph wiring
- `apps/api/src/graph/nodes.py` — node implementations + grounding prompt + self-grading
- `apps/api/tests/test_graph.py` — topology + loop tests
- [LangGraph docs](https://docs.langchain.com/oss/python/langgraph)
- ADR-0006 — multi-provider LLM Protocol (orthogonal to graph framework choice)
- ADR-0009 — Langfuse callback wraps the graph for observability
