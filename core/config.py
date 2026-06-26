"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Configuration module using pydantic-settings for environment variable loading
with optional API credentials, hardware constraints, and logging validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Any


class aetherisConfig(BaseSettings):
    """
    Central configuration for the aetheris multi-agent orchestration system.

    All values are loaded from environment variables (or a `.env` file).
    Prefix: aetheris_  (e.g. aetheris_OPENROUTER_API_KEY)
    """

    model_config = SettingsConfigDict(
        env_prefix="aetheris_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── API Keys (optional; blank values activate Simulation Mode) ───────

    OPENROUTER_API_KEY: str = Field(
        default="",
        description="API key for the OpenRouter inference gateway. Leave empty for Simulation Mode.",
    )
    NVIDIA_NIM_API_KEY: str = Field(
        default="",
        description="API key for NVIDIA NIM micro-services. Leave empty for Simulation Mode.",
    )
    GROQ_API_KEY: str = Field(
        default="",
        description="API key for Groq.",
    )
    GITHUB_TOKEN: str = Field(
        default="",
        description="GitHub models token.",
    )
    MISTRAL_API_KEY: str = Field(
        default="",
        description="API key for Mistral.",
    )
    GOOGLE_API_KEY: str = Field(
        default="",
        description="API key for Google AI Studio.",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="API key for OpenAI.",
    )
    KIE_API_KEY: str = Field(
        default="",
        description="API key for Kie.ai.",
    )
    UNLI_DEV_API_KEY: str = Field(
        default="",
        description="API key for UNLI.dev. Leave empty for Simulation Mode.",
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/aetheris",
        validation_alias="DATABASE_URL",
        description="PostgreSQL connection string using asyncpg",
    )

    JWT_SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        validation_alias="aetheris_JWT_SECRET_KEY",
        description="Secret key used for signing JWT tokens",
    )

    JWT_ALGORITHM: str = Field(
        default="HS256",
        validation_alias="aetheris_JWT_ALGORITHM",
        description="Algorithm used for signing JWT tokens",
    )

    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60,
        validation_alias="aetheris_JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        description="Duration in minutes that access tokens are valid for",
    )


    # ── Hardware Constraints (local fallback models) ─────────────────────

    LOCAL_MODEL_VRAM_LIMIT_MB: int = Field(
        default=6144,  # 6 GB = 6 × 1024 MB
        description=(
            "Hard ceiling (in MB) on VRAM that local fallback models may "
            "allocate. Defaults to 6 144 MB (6 GB) to prevent OOM crashes "
            "on the host GPU."
        ),
    )

    @field_validator("LOCAL_MODEL_VRAM_LIMIT_MB", mode="after")
    @classmethod
    def _enforce_vram_cap(cls, value: int) -> int:
        """
        Strictly cap VRAM allocation at 6 GB (6 144 MB).
        """
        max_allowed_mb = 6144  # 6 GB hard cap
        if value > max_allowed_mb:
            raise ValueError(
                f"LOCAL_MODEL_VRAM_LIMIT_MB={value} MB exceeds the 6 GB "
                f"({max_allowed_mb} MB) safety cap. Refusing to allocate "
                "more VRAM to prevent OOM crashes on the host GPU."
            )
        if value <= 0:
            raise ValueError(
                "LOCAL_MODEL_VRAM_LIMIT_MB must be a positive integer."
            )
        return value

    # ── Logging ──────────────────────────────────────────────────────────

    LOG_LEVEL: str = Field(
        default="INFO",
        description="Python logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    LOG_FORMAT: str = Field(
        default="%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
        description="Format string for Python's logging.Formatter.",
    )

    @field_validator("LOG_LEVEL", mode="after")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalised = value.upper().strip()
        if normalised not in allowed:
            raise ValueError(
                f"LOG_LEVEL must be one of {allowed}, got '{value}'."
            )
        return normalised

    # ── Lowercase Property Backwards Compatibility ──────────────────────

    @property
    def openrouter_api_key(self) -> str:
        return self.OPENROUTER_API_KEY

    @property
    def nvidia_nim_api_key(self) -> str:
        return self.NVIDIA_NIM_API_KEY

    @property
    def groq_api_key(self) -> str:
        return self.GROQ_API_KEY

    @property
    def github_token(self) -> str:
        return self.GITHUB_TOKEN

    @property
    def mistral_api_key(self) -> str:
        return self.MISTRAL_API_KEY

    @property
    def google_api_key(self) -> str:
        return self.GOOGLE_API_KEY

    @property
    def openai_api_key(self) -> str:
        return self.OPENAI_API_KEY

    @property
    def kie_api_key(self) -> str:
        return self.KIE_API_KEY

    @property
    def unli_dev_api_key(self) -> str:
        return self.UNLI_DEV_API_KEY

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL


# ── Singleton accessor ───────────────────────────────────────────────────

_settings: aetherisConfig | None = None


def get_settings() -> aetherisConfig:
    """Return a cached, validated aetherisConfig instance (singleton)."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = aetherisConfig()  # type: ignore[call-arg]
    return _settings
