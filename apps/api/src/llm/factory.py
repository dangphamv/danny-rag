from src.config import get_settings
from src.llm.anthropic import AnthropicProvider
from src.llm.ollama import OllamaEmbedder, OllamaProvider
from src.llm.openai import OpenAIEmbedder, OpenAIProvider
from src.llm.protocol import Embedder, LLMProvider


def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embed_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set but EMBED_PROVIDER=openai")
        return OpenAIEmbedder(api_key=settings.openai_api_key.get_secret_value())
    if settings.embed_provider == "ollama":
        return OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
        )
    raise ValueError(f"Unknown embed provider: {settings.embed_provider}")


def get_llm() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set but LLM_PROVIDER=anthropic")
        return AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value())
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set but LLM_PROVIDER=openai")
        return OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    if settings.llm_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_llm_model,
        )
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
