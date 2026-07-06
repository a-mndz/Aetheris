"""Phase 1 — Provider subsystem targeted regression tests.

Covers HIGH-004 (private method access) and HIGH-012 (semaphore inflation bug).
"""

from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from api_gateway.rate_limiter import (
    AsyncAPIGateway,
    ProviderPool,
    ProviderState,
    ResourceManager,
)

pytestmark = pytest.mark.unit


class TestHIGH004PublicStateAccessor:
    def test_get_provider_state_returns_snapshot(self) -> None:
        pool = ProviderPool()
        pool.register_provider("local/sim", roles=["breaker"])
        snapshot = pool.get_provider_state("local/sim")
        assert isinstance(snapshot, ProviderState)
        assert snapshot.error_count == 0

    def test_get_provider_state_returns_none_for_unknown(self) -> None:
        pool = ProviderPool()
        assert pool.get_provider_state("does-not-exist") is None


class TestHIGH012SemaphoreBehaviour:
    @pytest.mark.asyncio
    async def test_acquire_consumes_single_permit(self) -> None:
        rm = ResourceManager()
        rm._ensure_provider_bucket("local/sim")
        # Saturate the semaphore with manual holds
        holds = []
        for _ in range(ResourceManager.GLOBAL_CONCURRENCY_LIMIT):
            await rm.global_semaphore.acquire()
            holds.append(True)
        # Now any further acquire should fail within the small timeout window
        acquired = await rm.acquire_resources(provider="local/sim", tokens=1)
        assert acquired is False
        for _ in holds:
            rm.global_semaphore.release()

    @pytest.mark.asyncio
    async def test_release_decrements_active_concurrency(self) -> None:
        rm = ResourceManager()
        rm._ensure_provider_bucket("local/sim")
        acquired_a = await rm.acquire_resources(provider="local/sim", tokens=1)
        acquired_b = await rm.acquire_resources(provider="local/sim", tokens=1)
        assert acquired_a and acquired_b
        # Release one, the next acquire should succeed.
        rm.release_resources(provider="local/sim")
        acquired_c = await rm.acquire_resources(provider="local/sim", tokens=1)
        assert acquired_c is True

    @pytest.mark.asyncio
    async def test_release_without_hold_does_not_inflate(self) -> None:
        rm = ResourceManager()
        rm._ensure_provider_bucket("local/sim")
        before = rm.global_semaphore._value
        rm.release_resources(provider="local/sim")  # Should NOT release
        assert rm.global_semaphore._value == before
