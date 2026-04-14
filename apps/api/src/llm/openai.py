import logging
from collections.abc import AsyncIterator
from typing import cast

from langfuse import get_client, observe
from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk

from src.llm.protocol import Message

# MTC-10: hard ceiling on output tokens.
HARD_MAX_TOKENS = 1024

log = logging.getLogger(__name__)


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        # MTC-11: text-embedding-3-small is 1536d. Switching requires an ADR.
        self._dimension = 1536 if model == "text-embedding-3-small" else 3072

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model

    @observe(as_type="generation", name="openai.embed")
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        batch_size = 100
        total_prompt_tokens = 0
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await self._client.embeddings.create(model=self._model, input=batch)
            out.extend(d.embedding for d in resp.data)
            total_prompt_tokens += resp.usage.prompt_tokens
        try:
            get_client().update_current_generation(
                model=self._model,
                usage_details={"input": total_prompt_tokens, "output": 0},
            )
        except Exception as exc:
            log.debug("langfuse update_current_generation failed: %s", exc)
        return out


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    @observe(name="openai.generate")
    async def generate(self, messages: list[Message], max_tokens: int = HARD_MAX_TOKENS) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=min(max_tokens, HARD_MAX_TOKENS),
        )
        return resp.choices[0].message.content or ""

    @observe(name="openai.astream")
    async def astream(
        self,
        messages: list[Message],
        max_tokens: int = HARD_MAX_TOKENS,
    ) -> AsyncIterator[str]:
        stream = cast(
            AsyncStream[ChatCompletionChunk],
            await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=min(max_tokens, HARD_MAX_TOKENS),
                stream=True,
            ),
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
