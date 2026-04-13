import logging
from functools import lru_cache

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from src.config import get_settings
from src.observability.redact import mask_payload

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_langfuse() -> Langfuse | None:
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        log.warning("Langfuse keys not set — observability disabled")
        return None
    client = Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        host=settings.langfuse_host,
        mask=mask_payload,
    )
    log.info("Langfuse client initialized: host=%s", settings.langfuse_host)
    return client


def get_callback_handler() -> CallbackHandler | None:
    """Return a Langfuse LangChain callback handler bound to the global client.

    Pass into LangGraph's `astream(config={"callbacks": [handler]})` to capture
    per-node spans automatically. LLM-level spans on top of node spans come
    from the `@observe()` decorators on the provider methods.

    Returns None if Langfuse keys are not configured — callers must handle
    this so the chat path still works without observability.
    """
    if get_langfuse() is None:
        return None
    return CallbackHandler()


def shutdown_langfuse() -> None:
    client = get_langfuse()
    if client is not None:
        client.flush()
