"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Configuration module using pydantic-settings for environment variable loading
with optional API credentials, hardware constraints, and logging validation.
"""

import logging
import os
from typing import Any, ClassVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class aetherisConfig(BaseSettings):
    """
    Central configuration for the aetheris multi-agent orchestration system.

    All values are loaded from environment variables (or a `.env` file).
    Prefix: aetheris_  (e.g. aetheris_OPENROUTER_API_KEY)
    """

    model_config = SettingsConfigDict(
        env_prefix="AETHERIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        # The ``aetheris_`` lowercase prefix remains documented for legacy
        # callers; uppercase ``AETHERIS_*`` is canonical because the
        # settings class uses ``case_sensitive=True``.
        env_ignore_empty=False,
    )

    # ── API Keys (optional; blank values activate Simulation Mode) ───────

    # CRIT-007 audit fix: each provider key is rejected when it contains
    # a hardcoded leak marker prefix that triggered the audit (e.g. live
    # ``sk-…`` OpenRouter keys, NVIDIA ``nvapi-…`` tokens, etc.).  Even when
    # operators delete the demo .env values, any keys that still cycle
    # through the environment are refused — defence in depth.

    LEAKED_KEY_PREFIXES: ClassVar[tuple[str, ...]] = (
        "sk-or-v1-",
        "sk-proj-",
        "sk-ZO",
        "nvapi-",
        "gsk_p",
        "github_pat_",
        "AQ.Ab8",
    )

    @classmethod
    def _sanitize_provider_key(cls, field_name: str, value: str) -> str:
        """Reject any non-empty key carrying a known live prefix (CRIT-007).

        Operators who intentionally want to use live keys sourced from
        the OS secret store (see ``secrets_bootstrap.py``) can opt in
        by exporting ``AETHERIS_ALLOW_LIVE_KEYS=1`` in the process
        environment before invoking the application.  This keeps the
        audit guard active for *unintended* loads (a key ending up in
        ``.env``, a typo'd CI secret, etc.) while letting developers
        run with their real keys when they knowingly choose to.

        The opt-in is logged so it leaves a paper trail in startup
        output — never a silent override.
        """
        if value and any(value.startswith(prefix) for prefix in cls.LEAKED_KEY_PREFIXES):
            if os.environ.get("AETHERIS_ALLOW_LIVE_KEYS") == "1":
                logger.warning(
                    "CRIT-007 override active (AETHERIS_ALLOW_LIVE_KEYS=1); "
                    "loading live %s. Audit trail: %s.",
                    field_name,
                    "intentional developer opt-in",
                )
                return value
            raise ValueError(f"Live API key prefix detected for {field_name}. Refusing to load.")
        return value

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

    @field_validator(
        "OPENROUTER_API_KEY",
        "NVIDIA_NIM_API_KEY",
        "GROQ_API_KEY",
        "GITHUB_TOKEN",
        "MISTRAL_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "KIE_API_KEY",
        "UNLI_DEV_API_KEY",
        mode="after",
    )
    @classmethod
    def _reject_live_provider_keys(cls, value: str) -> str:
        return cls._sanitize_provider_key("provider_key", value)

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/aetheris",
        validation_alias="DATABASE_URL",
        description="PostgreSQL connection string using asyncpg",
    )

    # HIGH-016: Database SSL is configurable via environment (Phase 1).
    DATABASE_SSL: bool = Field(
        default=False,
        validation_alias="DATABASE_SSL",
        description=(
            "Enable SSL for database connections.  Default off to keep local "
            "development friction-free; production deployments MUST set this to true."
        ),
    )

    # CRIT-004: explicit CORS allowlist.  Wildcards combined with credentials
    # are forbidden by the CORS spec; we read a comma-separated allowlist
    # from CORS_ORIGINS and refuse the wildcard.
    CORS_ORIGINS: str = Field(
        default="http://localhost:5173,http://localhost:8000,http://127.0.0.1:8000",
        validation_alias="CORS_ORIGINS",
        description=(
            "Comma-separated explicit origin allowlist used by the CORS middleware. "
            "Wildcards are rejected to preserve authenticated session semantics."
        ),
    )

    # MED-019 / MED-021 helpers for Authentication middleware.
    AUTH_COOKIE_NAME: str = Field(
        default="aetheris_auth",
        validation_alias="AETHERIS_AUTH_COOKIE_NAME",
        description="Name of the httpOnly session cookie used for JWT delivery.",
    )

    # HIGH-014: per-IP rate limit on /auth/login and /auth/register.
    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(
        default=5,
        validation_alias="AETHERIS_AUTH_RATE_LIMIT_PER_MINUTE",
        description="Maximum number of /auth/* requests a single IP may issue per minute.",
    )

    JWT_SECRET_KEY: str = Field(
        default="",
        validation_alias="AETHERIS_JWT_SECRET_KEY",
        description=(
            "REQUIRED: secret key used for signing JWT tokens.  Set via "
            "AETHERIS_JWT_SECRET_KEY environment variable.  Application "
            "startup rejects the empty default (CRIT-005)."
        ),
    )

    # CRIT-005 audit finding: a hardcoded fallback secret makes every
    # shipped install forgeable; reject any value not provided by the
    # operator and enforce a minimum key length.
    _FORBIDDEN_JWT_DEFAULTS: ClassVar[set[str]] = {
        "",
        "change-me",
        "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
    }
    MIN_JWT_SECRET_LENGTH: ClassVar[int] = 32

    @field_validator("JWT_SECRET_KEY", mode="after")
    @classmethod
    def _reject_default_or_weak_secret(cls, value: str) -> str:
        """Refuse to start with the canonical demo fallback or a weak key (CRIT-005)."""
        if value in cls._FORBIDDEN_JWT_DEFAULTS:
            raise ValueError(
                "JWT_SECRET_KEY must be set to a non-default value via "
                "the aetheris_JWT_SECRET_KEY environment variable. "
                "An empty/known-demo value is refused because JWTs would "
                "be forgeable."
            )
        if len(value) < cls.MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                "JWT_SECRET_KEY must be at least "
                f"{cls.MIN_JWT_SECRET_LENGTH} characters long."
            )
        return value

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
