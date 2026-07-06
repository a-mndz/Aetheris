"""Phase 1 — Pipeline subsystem regression tests.

These tests verify the legacy/decision-engine boundary, claim-extraction
toggle, and fire-and-forget task safety added during Phase 1.
Phase 1 implementation files MUST be present for these to pass.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

from orchestrator.pipelines import run_micro_mode
from orchestrator.decisions import DecisionEngine, DecisionStrategy


pytestmark = pytest.mark.unit


def test_legacy_decision_engine_helper_available() -> None:
    """Run-with-decision-engine helper exists and exposes the new safety hook."""
    from orchestrator import pipelines
    assert hasattr(pipelines, "_is_claim_extraction_enabled")
    assert callable(pipelines._is_claim_extraction_enabled)
    assert callable(pipelines._legacy_pipeline_blocked_msg)


def test_decision_engine_exposes_safe_task_helper() -> None:
    from orchestrator import decisions
    assert hasattr(decisions, "safe_create_task_broadcast")
    assert callable(decisions.safe_create_task_broadcast)
