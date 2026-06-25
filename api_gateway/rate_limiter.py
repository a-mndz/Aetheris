"""
Aetheris — Adaptive Multi-Model Reasoning Orchestrator
Absolute Network Boundary (The Shield) - Rate Limiter & Health tracking.

This module enforces rate-limiting (concurrency limits), dynamic pre-request
jitter, retry-with-backoff, and provider circuit breaking/cooldown.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from api_gateway.client import AsyncHTTPClient
from api_gateway.strategy import ProviderStrategy

logger = logging.getLogger(__name__)

# ── Type aliases ─────────────────────────────────────────────────────────
AsyncModelCaller = Callable[[str, str, Optional[str]], Coroutine[Any, Any, str]]

# ── Defaults ─────────────────────────────────────────────────────────────
_DEFAULT_MAX_CONCURRENCY = 5
_DEFAULT_JITTER_MIN_SEC = 0.05
_DEFAULT_JITTER_MAX_SEC = 0.50


def extract_provider_key(model: str) -> str:
    """
    Derive a circuit-breaker key from a model identifier.

    Uses up to the first two path segments so that models behind the same
    gateway but served by different upstream providers get independent
    health tracking.  For example:

    * ``'openrouter/anthropic/claude-sonnet-4.6'`` → ``'openrouter/anthropic'``
    * ``'openrouter/openai/gpt-4o-mini'``          → ``'openrouter/openai'``
    * ``'nvidia/meta/llama-3.1-70b-instruct'``     → ``'nvidia/meta'``
    * ``'local/phi-3'``                            → ``'local/phi-3'``
    * ``'unknown'``                                → ``'unknown'``
    """
    parts = model.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


# ── Provider Health Tracking & Cooldown ─────────────────────────────────

class ProviderStatus(str, Enum):
    """Possible health states for an LLM provider."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DEAD = "dead"


@dataclass
class ProviderState:
    """Mutable health record for a single provider."""
    status: ProviderStatus = ProviderStatus.HEALTHY
    error_count: int = 0
    last_failure_timestamp: Optional[float] = None
    cooldown_until: Optional[float] = None
    roles: list[str] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        """
        True when the provider can accept requests right now.

        Note: for DEAD providers, availability returns True once the cooldown
        has expired.  This acts as an implicit 'half-open' check — the next
        request serves as the probe.  If it fails, ``report_failure`` /
        ``mark_provider_dead`` will re-trip the breaker.  An explicit
        half-open state machine is not implemented.
        """
        if self.status is ProviderStatus.DEAD:
            # Allow resurrection after cooldown expires.
            if self.cooldown_until and time.time() >= self.cooldown_until:
                return True
            return False
        return True


class ProviderPool:
    """
    Tracks health, error counts, and cooldowns for providers.
    """

    def __init__(self, degrade_threshold: int = 3) -> None:
        self._providers: dict[str, ProviderState] = {}
        self._degrade_threshold = degrade_threshold
        self._priority_order: list[str] = []

    def register_provider(self, name: str, roles: list[str] | None = None) -> None:
        """Register a new provider with specific roles."""
        if name in self._providers:
            return
        self._providers[name] = ProviderState(roles=roles or [])
        self._priority_order.append(name)
        logger.info("Registered provider '%s' with roles %s.", name, roles or [])

    def report_success(self, provider_name: str) -> None:
        """Reset errors and restore health on success."""
        state = self._get_state(provider_name)
        if not state:
            return
        state.error_count = 0
        if state.status is not ProviderStatus.HEALTHY:
            logger.info("Provider '%s' recovered → HEALTHY.", provider_name)
        state.status = ProviderStatus.HEALTHY
        state.cooldown_until = None

    def report_failure(self, provider_name: str) -> None:
        """Record a failure and auto-degrade if threshold is breached."""
        state = self._get_state(provider_name)
        if not state:
            return
        state.error_count += 1
        state.last_failure_timestamp = time.time()
        logger.warning("Provider '%s' failure #%d.", provider_name, state.error_count)

        if state.error_count >= self._degrade_threshold and state.status is ProviderStatus.HEALTHY:
            state.status = ProviderStatus.DEGRADED
            logger.warning("Provider '%s' auto-degraded to DEGRADED.", provider_name)

    def mark_provider_dead(self, provider_name: str, cooldown_seconds: float = 60.0) -> None:
        """Immediately mark a provider as DEAD for a cooldown window."""
        state = self._get_state(provider_name)
        if not state:
            return
        state.status = ProviderStatus.DEAD
        state.cooldown_until = time.time() + cooldown_seconds
        logger.error(
            "Provider '%s' marked DEAD — cooldown %.0fs (until %.2f).",
            provider_name,
            cooldown_seconds,
            state.cooldown_until,
        )

    def is_provider_healthy(self, provider_name: str) -> bool:
        """Check if provider is available or has outlived its cooldown."""
        state = self._providers.get(provider_name)
        if not state:
            return True
        return state.is_available

    def get_healthy_provider(self, role: str) -> Optional[str]:
        """
        Find the best available provider for a role.

        .. note::
            Currently unused by ``execute_with_fallback`` which manages
            provider health inline.  Retained for future orchestrator
            enhancements (e.g. proactive routing, load-aware scheduling).
        """
        candidates = [name for name in self._priority_order if role in self._providers[name].roles]

        # 1. Prefer healthy
        for name in candidates:
            if self._providers[name].status is ProviderStatus.HEALTHY:
                return name

        # 2. Allow degraded
        for name in candidates:
            if self._providers[name].status is ProviderStatus.DEGRADED:
                return name

        # 3. Resurrect dead if cooldown expired
        for name in candidates:
            state = self._providers[name]
            if state.status is ProviderStatus.DEAD and state.is_available:
                state.status = ProviderStatus.DEGRADED
                state.error_count = 0
                logger.info("Resurrected expired provider '%s' to DEGRADED.", name)
                return name

        return None

    def get_status(self, provider_name: str) -> Optional[dict]:
        state = self._providers.get(provider_name)
        if not state:
            return None
        return {
            "provider": provider_name,
            "status": state.status.value,
            "error_count": state.error_count,
            "last_failure_timestamp": state.last_failure_timestamp,
            "cooldown_until": state.cooldown_until,
            "roles": state.roles,
            "is_available": state.is_available,
        }

    def get_all_statuses(self) -> list[dict]:
        return [self.get_status(name) for name in self._priority_order if name in self._providers]

    def _get_state(self, provider_name: str) -> Optional[ProviderState]:
        return self._providers.get(provider_name)


# ── Async API Gateway ───────────────────────────────────────────────────

class AsyncAPIGateway:
    """
    Concurrency-limited, jitter-aware API gateway with retry-with-backoff
    and fallback chain execution.
    """

    def __init__(
        self,
        client: AsyncHTTPClient | None = None,
        call_fn: AsyncModelCaller | None = None,
        *,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
        jitter_range: tuple[float, float] = (
            _DEFAULT_JITTER_MIN_SEC,
            _DEFAULT_JITTER_MAX_SEC,
        ),
    ) -> None:
        self._client = client or AsyncHTTPClient()
        self._call_fn = call_fn
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._jitter_min, self._jitter_max = jitter_range
        self._default_pool = ProviderPool()

        logger.info(
            "AsyncAPIGateway initialized — concurrency=%d, jitter=%.2f-%.2fs.",
            max_concurrency,
            self._jitter_min,
            self._jitter_max,
        )

    async def close(self) -> None:
        """Shut down the underlying HTTP client and release connection pool."""
        await self._client.close()

    async def execute_with_fallback(
        self,
        prompt: str,
        role: str,
        strategy: ProviderStrategy,
        pool: ProviderPool | None = None,
        system_prompt: Optional[str] = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Execute a prompt against the model chain for role, falling back
        on subsequent models upon failure.
        """
        if pool is None:
            pool = self._default_pool
            for model in strategy.get_model_chain(role):
                provider_name = extract_provider_key(model)
                pool.register_provider(provider_name, roles=[role])

        chain = strategy.get_model_chain(role)
        logger.info("Executing prompt for role '%s' — chain: %s", role, chain)

        errors: list[tuple[str, Exception]] = []

        for index, model in enumerate(chain):
            provider_name = extract_provider_key(model)

            if not pool.is_provider_healthy(provider_name):
                logger.warning(
                    "Skipping model '%s' because provider '%s' is dead or cooling down.",
                    model,
                    provider_name,
                )
                continue

            is_fallback = index > 0
            if is_fallback:
                logger.warning(
                    "Falling back to model '%s' (position %d/%d) for role '%s'.",
                    model,
                    index + 1,
                    len(chain),
                    role,
                )

            try:
                response = await self._guarded_call(model, prompt, system_prompt, history)
                pool.report_success(provider_name)
                logger.info(
                    "Model '%s' succeeded for role '%s' (attempt %d/%d).",
                    model,
                    role,
                    index + 1,
                    len(chain),
                )
                return response
            except Exception as exc:
                logger.error(
                    "Model '%s' failed for role '%s': %s: %s",
                    model,
                    role,
                    type(exc).__name__,
                    exc,
                )
                pool.report_failure(provider_name)
                # If the provider is degraded or hit multiple issues, mark DEAD
                state = pool._get_state(provider_name)
                if state and state.error_count >= pool._degrade_threshold:
                    pool.mark_provider_dead(provider_name)
                errors.append((model, exc))

        raise AllModelsExhaustedError(role=role, chain=chain, errors=errors)

    async def _guarded_call(self, model: str, prompt: str, system_prompt: Optional[str] = None, history: list[dict[str, str]] | None = None) -> str:
        """
        Execute a single call using retry-with-backoff, semaphore, and jitter.
        """
        max_retries = 3
        backoff_base = 1.5

        for attempt in range(max_retries):
            # Dynamic Jitter
            jitter = random.uniform(self._jitter_min, self._jitter_max)
            if attempt > 0:
                # Exponential backoff + jitter
                delay = (backoff_base ** attempt) + jitter
                logger.warning(
                    "Attempt %d failed for model %s. Retrying in %.2fs...",
                    attempt,
                    model,
                    delay,
                )
                await asyncio.sleep(delay)
            elif jitter > 0:
                await asyncio.sleep(jitter)

            async with self._semaphore:
                try:
                    start = time.monotonic()
                    logger.debug(
                        "Semaphore acquired — calling model '%s' (attempt %d).",
                        model,
                        attempt + 1,
                    )
                    
                    if self._call_fn:
                        response = await self._call_fn(model, prompt, system_prompt, history)
                    else:
                        response = await self._client.post_request(model, prompt, system_prompt, history)

                    elapsed = time.monotonic() - start
                    logger.debug("Model '%s' responded in %.2fs.", model, elapsed)
                    return response
                except Exception as exc:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(
                        "Exception on model '%s' attempt %d: %s",
                        model,
                        attempt + 1,
                        exc,
                    )

        raise RuntimeError("Retry loop exhausted without raising or returning.")


# ── Exceptions ───────────────────────────────────────────────────────────

class AllModelsExhaustedError(Exception):
    """Raised when every model in a fallback chain has failed."""

    def __init__(
        self,
        role: str,
        chain: list[str],
        errors: list[tuple[str, Exception]],
    ) -> None:
        self.role = role
        self.chain = chain
        self.errors = errors
        error_summary = "; ".join(
            f"{model}: {type(exc).__name__}({exc})" for model, exc in errors
        )
        super().__init__(
            f"All {len(chain)} models exhausted for role '{role}'. Errors: [{error_summary}]"
        )


# Legacy alias removed — use AsyncAPIGateway directly.
# (Previously: RateLimitingGateway = AsyncAPIGateway)
