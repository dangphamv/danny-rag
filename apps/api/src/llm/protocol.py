from collections.abc import AsyncIterator
from typing import Literal, Protocol, TypedDict, runtime_checkable


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@runtime_checkable
class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def model_name(self) -> str: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    async def generate(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
    ) -> str: ...

    def astream(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]: ...
