"""Centralised configuration.

Every setting the application reads comes from this module. Values are loaded
from environment variables (and from a local ``.env`` file in development), so
no secret is ever hard-coded and nothing else in the code base calls
``os.getenv``.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Used only when APP_ENV=dev/test so a fresh checkout can start. The validator
# below refuses to boot with this value (or any short secret) when APP_ENV=prod.
DEV_JWT_SECRET = "dev-only-insecure-secret-do-not-use-in-production"  # noqa: S105
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- application -------------------------------------------------------
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    max_body_bytes: int = Field(default=300_000, ge=1_024)
    cors_allow_origins: str = ""  # comma-separated list; empty disables CORS
    trust_proxy_headers: bool = False  # true only behind our own nginx/ALB
    docs_enabled: bool = True  # serve Swagger UI (/docs) and /openapi.json

    # --- authentication ----------------------------------------------------
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: Literal["HS256"] = "HS256"  # pinned; never taken from the token
    jwt_expire_minutes: int = Field(default=30, ge=1, le=1_440)
    admin_username: str = ""
    admin_password: str = ""
    metrics_scrape_token: str = ""  # optional static token for a Prometheus scraper

    # --- Qdrant (vector database, system of record) -------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_timeout_seconds: float = Field(default=5.0, gt=0)
    store_chat_content: bool = True  # false => store metadata only, no Q/A text

    # --- Redis -------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    chat_rate_limit: int = Field(default=20, ge=1)
    chat_rate_window_seconds: int = Field(default=60, ge=1)
    login_max_attempts: int = Field(default=5, ge=1)
    login_lockout_seconds: int = Field(default=300, ge=1)
    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=600, ge=1)

    # --- LLM gateway -------------------------------------------------------
    llm_provider: Literal["mock", "openai_compatible"] = "mock"
    llm_fallback_provider: Literal["", "mock", "openai_compatible"] = ""
    llm_allowed_models: str = ""  # comma-separated allowlist for the request "model" field
    llm_timeout_seconds: float = Field(default=15.0, gt=0)
    llm_overall_deadline_seconds: float = Field(default=40.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_backoff_base_seconds: float = Field(default=0.5, gt=0)
    llm_backoff_max_seconds: float = Field(default=8.0, gt=0)
    llm_max_concurrency: int = Field(default=20, ge=1)
    llm_queue_wait_seconds: float = Field(default=5.0, ge=0)
    llm_max_output_tokens: int = Field(default=512, ge=1)
    breaker_failure_threshold: int = Field(default=5, ge=1)
    breaker_reset_seconds: float = Field(default=30.0, gt=0)
    mock_latency_seconds: float = Field(default=0.0, ge=0)  # simulated LLM latency

    # OpenAI-compatible adapter (OpenAI, Groq, OpenRouter, Ollama, vLLM, ...)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = ""  # no default: model names change, read the provider docs
    openai_max_tokens_param: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"

    # --- RAG ---------------------------------------------------------------
    rag_enabled: bool = True
    rag_top_k: int = Field(default=4, ge=1, le=10)
    rag_score_threshold: float = Field(default=0.08, ge=0, le=1)
    rag_chunk_size: int = Field(default=800, ge=100)
    rag_chunk_overlap: int = Field(default=100, ge=0)
    rag_max_document_chars: int = Field(default=200_000, ge=1)
    embedding_provider: Literal["hash", "openai_compatible"] = "hash"
    embedding_dim: int = Field(default=2048, ge=8, le=8_192)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = ""

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.app_env == "prod" and (
            self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH
        ):
            raise ValueError(
                f"JWT_SECRET must be a random value of at least {MIN_JWT_SECRET_LENGTH} "
                "characters when APP_ENV=prod."
            )
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE.")
        if self.llm_fallback_provider == self.llm_provider:
            raise ValueError("LLM_FALLBACK_PROVIDER must differ from LLM_PROVIDER.")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def allowed_models(self) -> set[str]:
        return {m.strip() for m in self.llm_allowed_models.split(",") if m.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
