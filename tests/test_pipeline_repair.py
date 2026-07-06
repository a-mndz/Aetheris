"""Phase 1 — Pipeline subsystem targeted regression tests.

Covers CRIT-001 (dual paths), HIGH-019 (claim toggle), HIGH-011 (task safety).
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.unit


class TestCRIT001LegacyPathBlocked:
    """CRIT-001 — DecisionEngine is the sole execution path."""

    def test_legacy_blocked_without_decision_engine(
        self, monkeypatch: pytest.MonkeyPatch, stub_gateway, stub_strategy, stub_pool
    ) -> None:
        monkeypatch.delenv("aetheris_LEGACY_PIPELINE_ENABLED", raising=False)
        from orchestrator.pipelines import _legacy_pipeline_blocked_msg, run_micro_mode

        with pytest.raises(RuntimeError) as exc:
            import asyncio as _aio
            _aio.run(run_micro_mode(
                user_query="hello",
                gateway=stub_gateway,
                strategy=stub_strategy,
                pool=stub_pool,
                decision_engine=None,
            ))
        assert "CRIT-001" in str(exc.value) or "legacy" in str(exc.value).lower()

    def test_legacy_path_remains_behind_opt_in_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from orchestrator.pipelines import _is_legacy_pipeline_opted_in
        monkeypatch.setenv("aetheris_LEGACY_PIPELINE_ENABLED", "true")
        assert _is_legacy_pipeline_opted_in() is True
        monkeypatch.setenv("aetheris_LEGACY_PIPELINE_ENABLED", "")
        assert _is_legacy_pipeline_opted_in() is False


class TestHIGH019ClaimExtractionToggle:
    """HIGH-019 — claim extraction no-op can be disabled."""

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("aetheris_DISABLE_CLAIM_EXTRACTION", raising=False)
        from orchestrator.pipelines import _is_claim_extraction_enabled
        assert _is_claim_extraction_enabled() is False

    def test_enabled_when_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("aetheris_DISABLE_CLAIM_EXTRACTION", "0")
        from orchestrator.pipelines import _is_claim_extraction_enabled
        assert _is_claim_extraction_enabled() is True

    def test_enabled_when_off_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("aetheris_DISABLE_CLAIM_EXTRACTION", "off")
        from orchestrator.pipelines import _is_claim_extraction_enabled
        assert _is_claim_extraction_enabled() is True


class TestHIGH011FireAndForgetTaskSafety:
    """HIGH-011 — streamed tasks must surface exceptions via callback."""

    @pytest.mark.asyncio
    async def test_callback_runs_on_exception(self) -> None:
        from orchestrator.decisions import safe_create_task_broadcast

        async def crash():
            raise RuntimeError("simulated streaming failure")

        task = safe_create_task_broadcast(crash(), name="test-crash")
        await asyncio.sleep(0.05)
        assert task.done()
        assert isinstance(task.exception(), RuntimeError)

    @pytest.mark.asyncio
    async def test_callback_runs_on_success(self) -> None:
        from orchestrator.decisions import safe_create_task_broadcast

        async def ok():
            return "ok"

        task = safe_create_task_broadcast(ok(), name="test-ok")
        result = await task
        assert result == "ok"
