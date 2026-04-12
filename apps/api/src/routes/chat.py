import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from src.config import get_settings
from src.graph.build import get_compiled_graph
from src.limits import limiter
from src.observability.langfuse import get_callback_handler
from src.security import require_api_key

log = logging.getLogger(__name__)

# MTC-08: 20/min per IP. Rate string comes from Settings so prod can override.
CHAT_RATE_LIMIT = get_settings().chat_rate_limit

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _build_graph_config(session_id: str) -> dict[str, Any] | None:
    """Build the LangGraph invocation config with the Langfuse callback + tags.

    Returns None when Langfuse is not configured so we don't pass an empty
    callbacks list. The chat path still works without observability.
    """
    handler = get_callback_handler()
    if handler is None:
        return None
    settings = get_settings()
    return {
        "callbacks": [handler],
        "metadata": {
            "langfuse_session_id": session_id,
            "langfuse_user_id": "anonymous",
            "langfuse_tags": [settings.env, settings.llm_provider],
        },
    }


async def _event_stream(question: str, session_id: str) -> AsyncIterator[str]:
    graph = get_compiled_graph()
    initial = {"question": question, "session_id": session_id, "rewrite_count": 0}
    config = _build_graph_config(session_id)

    yield _sse({"type": "start", "session_id": session_id})

    try:
        # stream_mode="custom" surfaces writer({...}) emissions from nodes to
        # the SSE response. The Langfuse handler attached via `config` produces
        # a parallel stream of trace events that go directly to Langfuse.
        if config is not None:
            stream = graph.astream(initial, stream_mode="custom", config=config)
        else:
            stream = graph.astream(initial, stream_mode="custom")
        async for chunk in stream:
            yield _sse(chunk)
    except Exception as exc:
        log.exception("graph stream failed")
        yield _sse({"type": "error", "message": str(exc)})
        return

    yield _sse({"type": "done"})
    yield "data: [DONE]\n\n"


@router.post("")
@limiter.limit(CHAT_RATE_LIMIT)  # MTC-08: 20/min/IP
async def chat(
    request: Request,  # required by slowapi
    body: ChatRequest,
    _: None = Depends(require_api_key),  # MTC-07
) -> StreamingResponse:
    session_id = body.session_id or str(uuid.uuid4())
    log.info("chat session=%s q=%r", session_id, body.question)
    return StreamingResponse(
        _event_stream(body.question, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
