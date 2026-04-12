# 0006. Multi-provider LLM abstraction via a thin Protocol

- **Status**: Accepted
- **Date**: 2026-04-12
- **Deciders**: Danny Pham
- **BRD Topic**: BRD.01.3203 (Integration)

## Context

The project supports three LLM providers per BRD §3.6:

- **Anthropic Claude** (primary, sonnet-4-6)
- **OpenAI** (gpt-4o-mini for chat, text-embedding-3-small for embeddings)
- **Ollama** (local: llama3.1:8b for chat, nomic-embed-text for embeddings)

Switching providers must be a single env var change (`LLM_PROVIDER` / `EMBED_PROVIDER`) — no code changes. Each provider has subtly different streaming, message format, and tool-calling semantics that need to be normalized.

There's a hard ceiling per MTC-10: every provider must clamp `max_tokens` to `HARD_MAX_TOKENS = 1024` regardless of caller input.

## Decision

Define two `typing.Protocol` types in `src/llm/protocol.py`:

```python
class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...
    @property
    def model_name(self) -> str: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

class LLMProvider(Protocol):
    @property
    def model_name(self) -> str: ...
    async def generate(self, messages: list[Message], max_tokens: int = 1024) -> str: ...
    def astream(self, messages: list[Message], max_tokens: int = 1024) -> AsyncIterator[str]: ...
```

One implementation file per provider: `anthropic.py`, `openai.py` (carries both `OpenAIEmbedder` and `OpenAIProvider`), `ollama.py` (same).

A `factory.py` returns the right concrete instance based on `Settings.llm_provider` / `Settings.embed_provider`.

Every implementation enforces the `HARD_MAX_TOKENS = 1024` clamp internally — defense in depth for MTC-10.

## Rationale

- **Protocol over ABC**: structural typing matches Python idiom, doesn't force inheritance, plays well with `runtime_checkable` for tests
- **Each provider's idiosyncrasies stay in its own file**: leakage between providers is impossible because they don't import each other
- **Factory keeps the call sites clean**: `embedder = get_embedder()` is the only line that ever touches provider selection
- **Defense-in-depth `max_tokens` clamp**: even if a future caller passes `max_tokens=999999`, every provider clamps it. The constant `HARD_MAX_TOKENS` is grep-able for audit purposes
- **No LangChain wrapping**: the `langchain-anthropic` / `langchain-openai` / `langchain-ollama` packages exist but they add layers we don't need (Runnable interface, message wrapping). Talking to the native SDK directly is cleaner

## Consequences (the leakage points worth knowing)

This abstraction is leaky by design — the goal is *minimum surface area*, not *zero*. Future-you should know where the leaks are:

### Streaming chunk shape
- **Anthropic**: `client.messages.stream(...)` returns an async context manager; you iterate `stream.text_stream`. Token boundaries are not aligned to BPE — chunks can be partial words.
- **OpenAI**: `client.chat.completions.create(stream=True)` returns an async iterator of `ChatCompletionChunk` objects; you read `chunk.choices[0].delta.content` per chunk. Some chunks are empty.
- **Ollama**: NDJSON over HTTP (`/api/chat` with `stream: true`); each line is `{"message": {"content": "..."}, "done": false/true}`.
- **Normalization**: all three implementations expose `astream()` that yields `str` chunks. Empty chunks are filtered.

### System messages
- **Anthropic**: `system` is a top-level kwarg, separate from `messages`. The implementation uses `_split()` to extract it.
- **OpenAI**: `system` is the first message in the messages list with `role="system"`.
- **Ollama**: follows OpenAI convention.
- **Normalization**: callers always pass a `messages` list including the system message. Each implementation rearranges as needed.

### Token counting
- **Not yet implemented**. Each provider has its own tokenizer (Anthropic's tokenizer, `tiktoken` for OpenAI, the model-specific BPE for Ollama). When token counting becomes relevant (cost tracking, context budget enforcement), this becomes a new method on the Protocol — and a new ADR.

### Tool calling
- **Not yet implemented**. Each provider has substantially different tool-call semantics (Anthropic's tool_use blocks, OpenAI's function/tool messages, Ollama's nascent support). Tool use is out of scope for v1; will be a future ADR.

### Embedding batching
- **OpenAI**: supports batches up to 2048 inputs per call; we use batches of 100 for headroom.
- **Ollama**: no batched endpoint; we send one request per input. Slow but functional.

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| **Thin `Protocol` + per-provider impl files** | Minimal glue, swap-friendly, leakage stays local | Manual normalization of streaming/message/tool semantics | **Selected** — best fit for the constraints |
| `langchain-*` adapters directly | Pre-built normalization | Couples to LangChain version churn; obscures provider semantics | Rejected — defeats the learning goal |
| Direct vendor SDKs without abstraction | Maximum control | Have to duplicate streaming/message handling at every call site | Rejected — provider-switching becomes a refactor |
| LiteLLM proxy (separate process) | Single OpenAI-shaped API for all providers | Extra deployment, hides per-provider semantics | Rejected — adds infra and obscures the things the project wants to learn |
| ABCs instead of Protocols | Static typing benefits | Forces inheritance, more boilerplate | Rejected — Protocol is the modern Python idiom |

## References

- [BRD-01 §7.2 BRD.01.3203](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — Integration topic
- [BRD-01 §3.7 MTC-10](../01_BRD/BRD-01_rag_knowledge_chatbot/BRD-01_rag_knowledge_chatbot.md) — max_tokens ceiling
- `apps/api/src/llm/protocol.py` — Protocol definitions
- `apps/api/src/llm/{anthropic,openai,ollama,factory}.py` — implementations
- ADR-0008 — embedding model lock-in (related but separate concern)
