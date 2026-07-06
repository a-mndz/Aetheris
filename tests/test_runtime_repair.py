"""Phase 1 — Runtime subsystem targeted regression tests.

Covers HIGH-010 (timezone-aware datetime), HIGH-018 (XML caching), HIGH-009 (RuntimeEngine wiring).
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


class TestHIGH010TimezoneAwareDatetime:
    def test_stream_event_default_timestamp_is_tz_aware(self) -> None:
        from orchestrator.streaming import EventType, StreamEvent
        event = StreamEvent(event=EventType.PROGRESS, data={"step": 1})
        assert event.timestamp.tzinfo is not None

    def test_naive_timestamp_is_normalised(self) -> None:
        from orchestrator.streaming import EventType, StreamEvent
        naive = datetime(2026, 1, 1, 12, 0, 0)
        event = StreamEvent(event=EventType.PROGRESS, data={"step": 1}, timestamp=naive)
        assert event.timestamp.tzinfo is timezone.utc
        assert event.timestamp.utcoffset() == timedelta(0)

    def test_to_dict_isoformat_contains_offset(self) -> None:
        from orchestrator.streaming import EventType, StreamEvent
        event = StreamEvent(event=EventType.PROGRESS, data={"x": 1})
        iso = event.to_dict()["timestamp"]
        # Either +00:00 or Z suffix indicates explicit UTC.
        assert iso.endswith("+00:00") or iso.endswith("Z")


class TestHIGH018XPLCaching:
    def test_subsequent_calls_are_cached(self) -> None:
        from agents.prompt_manager import (
            clear_prompt_cache,
            load_runtime_contracts,
        )
        clear_prompt_cache()
        first = load_runtime_contracts()
        start = time.perf_counter()
        for _ in range(50):
            load_runtime_contracts()
        elapsed = time.perf_counter() - start
        # Cached calls should be sub-millisecond for 50 invocations.
        assert elapsed < 0.05
        assert len(first) == len(load_runtime_contracts())

    def test_clear_prompt_cache_resets(self) -> None:
        from agents.prompt_manager import (
            _load_runtime_contracts_cached,
            clear_prompt_cache,
        )
        _load_runtime_contracts_cached(None)
        assert _load_runtime_contracts_cached.cache_info().currsize >= 1
        clear_prompt_cache()
        assert _load_runtime_contracts_cached.cache_info().currsize == 0


class TestHIGH009RuntimeEngineWiring:
    def test_decision_engine_accepts_runtime_engine(self) -> None:
        from orchestrator.decisions import DecisionEngine, DecisionStrategy
        stub_runtime = object()
        engine = DecisionEngine(
            strategy=DecisionStrategy.PARALLEL,
            runtime_engine=stub_runtime,
        )
        assert engine.runtime_engine is stub_runtime

    @pytest.mark.asyncio
    async def test_dispatch_routes_through_runtime_when_configured(self) -> None:
        from orchestrator.decisions import DecisionEngine, DecisionStrategy

        class _RecordingRuntime:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def execute_with_contracts(self, **kwargs):
                self.calls.append(kwargs)
                return '{"answer":"runtime-output","confidence":0.8}'

        runtime = _RecordingRuntime()
        engine = DecisionEngine(
            strategy=DecisionStrategy.PARALLEL,
            runtime_engine=runtime,
        )

        class _StubGateway:
            async def execute_with_fallback(self, **kwargs):
                raise AssertionError("gateway must NOT be called when runtime_engine is wired")

        class _StubStrategy:
            class mode:
                value = "HYBRID"

        result = await engine._execute_logician(
            query="hello",
            gateway=_StubGateway(),
            strategy=_StubStrategy(),
            pool=None,
            passport=type("P", (), {"request_id": "req-1", "update_stage": lambda self, s: None})(),
            history=None,
        )
        assert runtime.calls, "RuntimeEngine.execute_with_contracts was not called"
        assert result.answer == "runtime-output"

    @pytest.mark.asyncio
    async def test_dispatch_falls_back_to_gateway(self) -> None:
        from orchestrator.decisions import DecisionEngine, DecisionStrategy

        engine = DecisionEngine(strategy=DecisionStrategy.PARALLEL, runtime_engine=None)

        class _StubGateway:
            def __init__(self) -> None:
                self.called = False
            async def execute_with_fallback(self, **kwargs):
                self.called = True
                return '{"answer":"gateway-output","confidence":0.7}'

        gw = _StubGateway()
        class _StubStrategy:
            class mode:
                value = "HYBRID"
        result = await engine._execute_logician(
            query="hello",
            gateway=gw,
            strategy=_StubStrategy(),
            pool=None,
            passport=type("P", (), {"request_id": "req-1", "update_stage": lambda self, s: None})(),
            history=None,
        )
        assert gw.called
        assert result.answer == "gateway-output"
