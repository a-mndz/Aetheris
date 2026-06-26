"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Provider strategy: mode-aware model selection with per-role fallback chains.

This module maps each system *role* (generation, breaker, judge) to a
prioritised list of LLM model identifiers.  Three operating modes govern
which models are considered:

* **FREE**   — community / open-weight models only (no API credit cost).
* **HYBRID** — prefers paid models but falls back to free alternatives.
* **PAID**   — premium, commercial-grade models with the highest quality.

The orchestrator calls :meth:`ProviderStrategy.get_model_chain` to obtain
an ordered list of models to attempt for a given role.  The first element
is the *primary* pick; subsequent elements are fallbacks tried in order
if an upstream call fails or times out.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, List

logger = logging.getLogger(__name__)


# ── Operating Modes ──────────────────────────────────────────────────────


class StrategyMode(str, Enum):
    """Supported provider-strategy operating modes."""

    FREE = "FREE"
    HYBRID = "HYBRID"
    PAID = "PAID"


# ── Model Maps ───────────────────────────────────────────────────────────
# Each map is a ``{role: [primary, fallback_1, …]}`` dictionary.
# Models are specified as OpenRouter-style identifiers so the downstream
# ``provider_pool`` can route them to the correct gateway.

FREE_MODELS: Dict[str, List[str]] = {
    "generation": [
        "google/gemini-2.5-flash",
        "github/meta-llama-3.1-70b-instruct",
        "groq/llama-3.3-70b-versatile",
    ],
    "breaker": [
        "google/gemini-2.5-flash",
        "groq/llama-3.1-8b-instant",
    ],
    "judge": [
        "google/gemini-2.5-pro",
        "github/meta-llama-3.1-70b-instruct",
    ],
}

HYBRID_MODELS: Dict[str, List[str]] = {
    "generation": [
        "unli/deepseek-chat",
        "groq/llama-3.3-70b-versatile",
        "openai/gpt-4o-mini",
    ],
    "breaker": [
        "unli/gpt-4o-mini",
        "groq/llama-3.1-8b-instant",
        "openai/gpt-4o-mini",
    ],
    "judge": [
        "unli/gpt-4o",
        "kie/deepseek-chat",
        "google/gemini-2.5-pro",
    ],
}

PAID_MODELS: Dict[str, List[str]] = {
    "generation": [
        "openrouter/anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "unli/deepseek-chat",
    ],
    "breaker": [
        "openai/gpt-4o-mini",
        "unli/gpt-4o-mini",
        "openrouter/anthropic/claude-3.5-sonnet",
    ],
    "judge": [
        "openrouter/anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "unli/gpt-4o",
    ],
}

# ── Lookup Table ─────────────────────────────────────────────────────────

_MODE_TO_MAP: Dict[StrategyMode, Dict[str, List[str]]] = {
    StrategyMode.FREE: FREE_MODELS,
    StrategyMode.HYBRID: HYBRID_MODELS,
    StrategyMode.PAID: PAID_MODELS,
}


# ── Strategy Class ───────────────────────────────────────────────────────


class ProviderStrategy:
    """
    Mode-aware model selector with per-role fallback chains.

    Parameters
    ----------
    mode:
        One of ``'FREE'``, ``'HYBRID'``, or ``'PAID'`` (case-insensitive).

    Raises
    ------
    ValueError
        If *mode* is not a recognised :class:`StrategyMode`.

    Examples
    --------
    >>> strategy = ProviderStrategy("HYBRID")
    >>> strategy.get_model_chain("generation")
    ['openrouter/anthropic/claude-sonnet-4.6', 'openrouter/openai/gpt-4o-mini', 'openrouter/meta-llama/llama-3-8b-instruct']
    """

    def __init__(self, mode: str) -> None:
        try:
            self._mode = StrategyMode(mode.upper())
        except ValueError:
            valid = ", ".join(m.value for m in StrategyMode)
            raise ValueError(
                f"Unknown strategy mode '{mode}'. Must be one of: {valid}."
            ) from None

        self._model_map = _MODE_TO_MAP[self._mode]
        logger.info("ProviderStrategy initialised in %s mode.", self._mode.value)

    # ── Public Properties ────────────────────────────────────────────

    @property
    def mode(self) -> StrategyMode:
        """The active operating mode."""
        return self._mode

    @property
    def supported_roles(self) -> list[str]:
        """Roles for which model chains are defined in the active mode."""
        return list(self._model_map.keys())

    # ── Core API ─────────────────────────────────────────────────────

    def get_model_chain(self, role: str) -> list[str]:
        """
        Return a fallback-ordered list of models for *role*.

        The first element is the primary model; subsequent elements are
        fallbacks tried in sequence if earlier candidates fail.

        The returned list always contains **at least two** entries
        (primary + ≥1 fallback).  If the active mode's map for a role
        somehow contains fewer than two models, models from lower-cost
        tiers are appended automatically.

        Parameters
        ----------
        role:
            System role identifier — typically ``'generation'``,
            ``'breaker'``, or ``'judge'``.

        Returns
        -------
        list[str]
            Non-empty, ordered list of model identifiers.

        Raises
        ------
        ValueError
            If *role* is not defined in **any** mode's model map.
        """
        chain = list(self._model_map.get(role, []))

        # If the role is entirely absent from the active map, try to pull
        # models from another tier so the system degrades gracefully.
        if not chain:
            chain = self._cross_tier_fallback(role)

        if not chain:
            available = ", ".join(
                sorted(
                    {r for m in _MODE_TO_MAP.values() for r in m}
                )
            )
            raise ValueError(
                f"Role '{role}' is not defined in any strategy mode. "
                f"Available roles: {available}."
            )

        # Guarantee at least two entries (primary + fallback).
        if len(chain) < 2:
            extras = self._cross_tier_fallback(role, exclude=chain)
            chain.extend(extras[: 2 - len(chain)])

        logger.debug(
            "Model chain for role '%s' (%s mode): %s",
            role,
            self._mode.value,
            chain,
        )
        return chain

    # ── Private Helpers ──────────────────────────────────────────────

    def _cross_tier_fallback(
        self,
        role: str,
        exclude: list[str] | None = None,
    ) -> list[str]:
        """
        Collect models for *role* from **other** tiers (FREE → PAID order)
        that are not already in *exclude*.

        This ensures a fallback chain can always be constructed even when
        the active mode has a thin mapping for a particular role.
        """
        exclude_set = set(exclude or [])

        # Walk tiers in cheapest-first order so free models are preferred
        # as ultimate fallbacks regardless of the active mode.
        tier_order = [StrategyMode.FREE, StrategyMode.HYBRID, StrategyMode.PAID]

        result: list[str] = []
        for tier in tier_order:
            if tier is self._mode:
                continue  # Already consumed.
            for model in _MODE_TO_MAP[tier].get(role, []):
                if model not in exclude_set and model not in result:
                    result.append(model)
        return result
