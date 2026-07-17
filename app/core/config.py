"""Application configuration.

All configuration is loaded and validated through pydantic-settings. Secrets are
wrapped in ``SecretStr`` so they are never accidentally logged or serialised, and
every value is validated at process start-up (fail-fast) rather than at first use.

Precedence (highest first):
    1. Real environment variables
    2. The ``.env`` file for the active ``APP_ENV``  (e.g. ``.env.development``)
    3. The base ``.env`` file
    4. The defaults declared below
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


def _env_files() -> tuple[str, ...]:
    """Return the ``.env`` files to load, most specific last (wins)."""
    active = os.getenv("APP_ENV", "development")
    return (".env", f".env.{active}")


class LLMProviderConfig(BaseSettings):
    """A single OpenAI-compatible LLM provider entry.

    Groq, Gemini (OpenAI-compat endpoint), OpenRouter, Together, Atlas Cloud, and
    a local Ollama/vLLM server are all wire-compatible with ``ChatOpenAI`` — you
    only change ``base_url`` + ``api_key`` + ``model``.
    """

    name: str
    model: str
    base_url: str
    api_key: SecretStr
    # Priority used by the circular-fallback LLM service (lower = tried first).
    priority: int = 100
    temperature: float = 0.1
    max_tokens: int = 1024
    timeout_s: float = 30.0


class Settings(BaseSettings):
    """Root application settings."""

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core -------------------------------------------------------------
    app_name: str = "career-copilot-agent"
    app_env: Environment = Environment.DEVELOPMENT
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    # --- Security / Auth --------------------------------------------------
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("change-me-in-production-use-a-64-char-random-string"),
        description="HMAC signing key for JWT session tokens.",
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 1 day
    # Comma-separated list is coerced to a list by the validator below. NoDecode
    # tells pydantic-settings not to JSON-parse this env var itself (it would
    # fail on a bare "*" or "a, b") — the mode="before" validator handles it.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # --- Rate limiting ----------------------------------------------------
    rate_limit_default: str = "60/minute"
    rate_limit_chat: str = "20/minute"

    # --- Database (Postgres + pgvector) -----------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: SecretStr = SecretStr("postgres")
    postgres_db: str = "career_copilot"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- LLM providers (populated from env, see _load_providers) ----------
    # Kept out of BaseSettings direct parsing because each provider is a small
    # object built from a flat set of env vars for ergonomics on free tiers.
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    llm_total_timeout_s: float = 60.0
    llm_max_retries: int = 2  # per-provider tenacity retries before fallback

    # Provider 1 (primary) — OpenAI (paid; cheap + reliable, great at routing/tool-calling).
    llm1_name: str = "openai"
    llm1_model: str = "gpt-4o-mini"
    llm1_base_url: str = "https://api.openai.com/v1"
    llm1_api_key: SecretStr = SecretStr("")
    # Provider 2 (fallback) — Groq. gpt-oss-120b (not llama-3.3-70b-versatile) because
    # it supports json_schema structured outputs (needed by RouterDecision/TriageResult)
    # and is Groq's recommended replacement ahead of llama-3.3-70b-versatile's
    # free-tier deprecation (2026-08-16).
    llm2_name: str = "groq"
    llm2_model: str = "openai/gpt-oss-120b"
    llm2_base_url: str = "https://api.groq.com/openai/v1"
    llm2_api_key: SecretStr = SecretStr("")
    # Provider 3 (fallback) — defaults target Gemini's OpenAI-compat endpoint.
    llm3_name: str = "gemini"
    llm3_model: str = "gemini-2.0-flash"
    llm3_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm3_api_key: SecretStr = SecretStr("")
    # Provider 4 — unused by default; fill in to add a 4th fallback.
    llm4_name: str = ""
    llm4_model: str = ""
    llm4_base_url: str = ""
    llm4_api_key: SecretStr = SecretStr("")

    # --- Embeddings (local, free, CPU-friendly via fastembed) -------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384  # must match the model above

    # --- Job search (Adzuna API — free tier, register at developer.adzuna.com)
    adzuna_app_id: SecretStr = SecretStr("")
    adzuna_app_key: SecretStr = SecretStr("")
    adzuna_default_country: str = "gb"  # gb, us, in, de, ca, au, ...

    # --- Retrieval / Hybrid search ----------------------------------------
    retrieval_top_k: int = 5
    retrieval_candidate_k: int = 20  # per-retriever pool before fusion
    rrf_k: int = 60  # Reciprocal Rank Fusion constant
    retrieval_min_score: float = 0.0

    # --- Guardrails -------------------------------------------------------
    guardrails_enabled: bool = True
    guardrail_max_input_chars: int = 8000
    guardrail_block_pii_output: bool = True
    guardrail_min_groundedness: float = 0.30  # citation-overlap threshold

    # --- Observability ----------------------------------------------------
    langfuse_tracing_enabled: bool = False
    langfuse_public_key: SecretStr = SecretStr("")
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_host: str = "https://cloud.langfuse.com"
    metrics_enabled: bool = True

    # --- Human-in-the-loop ------------------------------------------------
    escalation_email: str = "support-leads@example.com"

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _validate_production_safety(self) -> Settings:
        """Fail fast in production if insecure defaults were left in place."""
        if self.app_env == Environment.PRODUCTION:
            if self.jwt_secret_key.get_secret_value().startswith("change-me"):
                raise ValueError("JWT_SECRET_KEY must be set in production.")
            if self.debug:
                raise ValueError("DEBUG must be false in production.")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must not be '*' in production.")
        return self

    # ------------------------------------------------------------------ #
    # Derived helpers
    # ------------------------------------------------------------------ #
    @property
    def async_database_url(self) -> str:
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def checkpointer_dsn(self) -> str:
        """Plain libpq DSN for the LangGraph Postgres checkpointer (no driver suffix)."""
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def llm_providers(self) -> list[LLMProviderConfig]:
        """Build the ordered list of *configured* LLM providers.

        A provider is included only when its API key is present (or when it is a
        localhost endpoint, which needs no key). Providers are returned sorted by
        priority so the fallback service tries the primary first.
        """
        raw = [
            (1, self.llm1_name, self.llm1_model, self.llm1_base_url, self.llm1_api_key),
            (2, self.llm2_name, self.llm2_model, self.llm2_base_url, self.llm2_api_key),
            (3, self.llm3_name, self.llm3_model, self.llm3_base_url, self.llm3_api_key),
            (4, self.llm4_name, self.llm4_model, self.llm4_base_url, self.llm4_api_key),
        ]
        providers: list[LLMProviderConfig] = []
        for prio, name, model, base_url, key in raw:
            is_local = "localhost" in base_url or "127.0.0.1" in base_url
            if not key.get_secret_value() and not is_local:
                continue
            providers.append(
                LLMProviderConfig(
                    name=name,
                    model=model,
                    base_url=base_url,
                    api_key=key if key.get_secret_value() else SecretStr("not-needed"),
                    priority=prio,
                    temperature=self.llm_temperature,
                    max_tokens=self.llm_max_tokens,
                    timeout_s=self.llm_total_timeout_s,
                )
            )
        return sorted(providers, key=lambda p: p.priority)


@lru_cache
def get_settings() -> Settings:
    """Return the cached, validated settings singleton."""
    return Settings()


settings = get_settings()
