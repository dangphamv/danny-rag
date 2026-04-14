import json
from collections.abc import AsyncIterator

import httpx
from langfuse import observe

from src.llm.protocol import Message

# MTC-10: hard ceiling on output tokens.
HARD_MAX_TOKENS = 1024


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str = "nomic-embed-text") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = 768  # nomic-embed-text default

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        async with httpx.AsyncClient(base_url=self._base_url, timeout=60.0) as client:
            for text in texts:
                resp = await client.post(
                    "/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                out.append(resp.json()["embedding"])
        return out


class OllamaProvider:
    def __init__(self, base_url: str, model: str = "llama3.1:8b") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    @observe(name="ollama.generate")
    async def generate(self, messages: list[Message], max_tokens: int = HARD_MAX_TOKENS) -> str:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=120.0) as client:
            resp = await client.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": min(max_tokens, HARD_MAX_TOKENS)},
                },
            )
            resp.raise_for_status()
            content: str = resp.json()["message"]["content"]
            return content

    @observe(name="ollama.astream")
    async def astream(
        self,
        messages: list[Message],
        max_tokens: int = HARD_MAX_TOKENS,
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=120.0) as client:
            async with client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": True,
                    "options": {"num_predict": min(max_tokens, HARD_MAX_TOKENS)},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
