import logging
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam
from langfuse import get_client, observe

from src.llm.protocol import Message

# MTC-10: hard ceiling on output tokens. Provider clamps even if caller passes more.
HARD_MAX_TOKENS = 1024

log = logging.getLogger(__name__)


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    @staticmethod
    def _split(messages: list[Message]) -> tuple[str | None, list[MessageParam]]:
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        rest: list[MessageParam] = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] != "system"
        ]
        return system, rest

    def _record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Enrich the current Langfuse generation observation with model + usage.

        Wrapped in try/except so observability failures never break the chat path.
        Langfuse uses model + usage_details to compute cost from its model price
        catalog — see https://langfuse.com/docs/model-usage-and-cost.
        """
        try:
            get_client().update_current_generation(
                model=self._model,
                usage_details={
                    "input": input_tokens,
                    "output": output_tokens,
                },
            )
        except Exception as exc:
            log.debug("langfuse update_current_generation failed: %s", exc)

    @observe(as_type="generation", name="anthropic.generate")
    async def generate(self, messages: list[Message], max_tokens: int = HARD_MAX_TOKENS) -> str:
        system, rest = self._split(messages)
        capped = min(max_tokens, HARD_MAX_TOKENS)
        if system is not None:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=capped,
                messages=rest,
                system=system,
            )
        else:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=capped,
                messages=rest,
            )
        self._record_usage(resp.usage.input_tokens, resp.usage.output_tokens)
        return "".join(block.text for block in resp.content if hasattr(block, "text"))

    @observe(as_type="generation", name="anthropic.astream")
    async def astream(
        self,
        messages: list[Message],
        max_tokens: int = HARD_MAX_TOKENS,
    ) -> AsyncIterator[str]:
        system, rest = self._split(messages)
        capped = min(max_tokens, HARD_MAX_TOKENS)
        if system is not None:
            ctx = self._client.messages.stream(
                model=self._model,
                max_tokens=capped,
                messages=rest,
                system=system,
            )
        else:
            ctx = self._client.messages.stream(
                model=self._model,
                max_tokens=capped,
                messages=rest,
            )
        async with ctx as stream:
            async for text in stream.text_stream:
                yield text
            # After the stream is fully consumed, Anthropic exposes the totals via
            # get_final_message().usage. We're still inside the @observe context,
            # so update_current_generation attaches to this generation observation.
            try:
                final = await stream.get_final_message()
                self._record_usage(final.usage.input_tokens, final.usage.output_tokens)
            except Exception as exc:
                log.debug("get_final_message failed: %s", exc)
