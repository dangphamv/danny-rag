from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = Field(default="local")
    api_version: str = Field(default="0.1.0")

    api_key: SecretStr = Field(default=SecretStr("dev-local-key-change-me"))
    allowed_origins: str = Field(default="http://localhost:3000")

    llm_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    embed_provider: Literal["openai", "ollama"] = "openai"

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None

    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "http://localhost:3001"

    # Wired but inactive — the LangGraph Postgres checkpointer is not yet
    # attached to the compiled graph. See ADR-0005 and DEPLOY.md "Known gaps".
    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"

    max_output_tokens: int = 1024  # MTC-10

    chat_rate_limit: str = "20/minute"  # MTC-08
    ingest_rate_limit: str = "5/minute"  # MTC-08

    upload_max_bytes: int = 25 * 1024 * 1024  # MTC-09
    ingest_timeout_seconds: int = 60  # MTC-09
    ingest_max_concurrent: int = 2  # MTC-09
    upload_allowed_mime_types: tuple[str, ...] = (  # MTC-09
        "application/pdf",
        "text/markdown",
        "text/html",
        "text/plain",
    )

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def qdrant_collection(self) -> str:
        # MTC-01: collection name encodes the embedder so dimensions never mix.
        suffix = {
            "openai": "text-embedding-3-small",
            "ollama": self.ollama_embed_model,
        }[self.embed_provider]
        return f"chunks_{suffix}"

    @property
    def embedding_dimension(self) -> int:
        # MTC-11: text-embedding-3-small is locked at 1536d.
        return {"openai": 1536, "ollama": 768}[self.embed_provider]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
