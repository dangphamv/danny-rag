import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import ExitStack
from typing import Any

from fastapi import APIRouter, Depends, Request
from langfuse import propagate_attributes
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from src.config import get_settings
from src.graph.build import get_compiled_graph
from src.limits import limiter
from src.observability.langfuse import get_callback_handler, get_langfuse
from src.observability.redact import hash_text
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


async def _event_stream(question: str, session_id: str) -> AsyncIterator[str]:
    graph = get_compiled_graph()
    initial = {"question": question, "session_id": session_id, "rewrite_count": 0}

    settings = get_settings()
    handler = get_callback_handler()
    lf = get_langfuse()

    yield _sse({"type": "start", "session_id": session_id})

    # Langfuse v4 requires an enclosing OTEL span for the LangChain
    # CallbackHandler + @observe() decorators to share a trace context. Without
    # it, each provider.generate() / provider.astream() creates its own root
    # trace and session/tags never attach. See propagate_attributes docstring
    # in langfuse/_client/propagation.py.
    with ExitStack() as stack:
        if lf is not None:
            stack.enter_context(
                lf.start_as_current_observation(
                    name="chat-turn",
                    input={"q_hash": hash_text(question)},
                )
            )
            stack.enter_context(
                propagate_attributes(
                    session_id=session_id,
                    user_id="anonymous",
                    tags=[settings.env, settings.llm_provider],
                )
            )

        config: dict[str, Any] | None = (
            {"callbacks": [handler]} if handler is not None else None
        )

        try:
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
    log.info("chat session=%s q=%s", session_id, hash_text(body.question))
    return StreamingResponse(
        _event_stream(body.question, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
