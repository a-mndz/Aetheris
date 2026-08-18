"""Tests for orchestrator/repair.py — reflection / repair loop (RFC-003 §9)."""

from __future__ import annotations

import pytest

from core.schemas import PipelineBudget
from orchestrator.budget import TokenBudgetManager
from orchestrator.repair import (
    ACTIONABLE_DEFECTS,
    Defect,
    RepairResult,
    run_repair_loop,
)


def _budget_mgr() -> TokenBudgetManager:
    return TokenBudgetManager()


def _defect(kind: str = "contradiction", description: str = "test defect") -> Defect:
    return Defect(kind=kind, description=description)


# ── basic behavior ────────────────────────────────────────────────────

def test_no_defects_returns_original_output() -> None:
    result = run_repair_loop(
        generated_output="original",
        judge_defects=[],
        budget_manager=_budget_mgr(),
        budget=PipelineBudget(),
    )
    assert result.output == "original"
    assert result.repaired is False
    assert result.repair_count == 0


def test_non_actionable_defects_are_ignored() -> None:
    result = run_repair_loop(
        generated_output="original",
        judge_defects=[Defect(kind="style_nit", description="minor")],
        budget_manager=_budget_mgr(),
        budget=PipelineBudget(),
    )
    assert result.repaired is False


def test_repair_succeeds_on_first_cycle() -> None:
    def repair_fn(output, defects):
        return "fixed"

    def rejudge_fn(output):
        return []  # clean

    result = run_repair_loop(
        generated_output="broken",
        judge_defects=[_defect()],
        budget_manager=_budget_mgr(),
        budget=PipelineBudget(),
        repair_fn=repair_fn,
        rejudge_fn=rejudge_fn,
    )
    assert result.output == "fixed"
    assert result.repaired is True
    assert result.bypassed is False
    assert result.repair_count == 1


def test_repair_succeeds_on_second_cycle() -> None:
    call_count = 0

    def repair_fn(output, defects):
        nonlocal call_count
        call_count += 1
        return f"attempt-{call_count}"

    def rejudge_fn(output):
        if output == "attempt-1":
            return [_defect("math_error", "still wrong")]
        return []

    result = run_repair_loop(
        generated_output="broken",
        judge_defects=[_defect()],
        budget_manager=_budget_mgr(),
        budget=PipelineBudget(),
        repair_fn=repair_fn,
        rejudge_fn=rejudge_fn,
    )
    assert result.output == "attempt-2"
    assert result.repaired is True
    assert result.bypassed is False
    assert result.repair_count == 2


# ── max_repairs cap ───────────────────────────────────────────────────

def test_stops_at_max_repairs_with_caveats() -> None:
    def repair_fn(output, defects):
        return output

    def rejudge_fn(output):
        return [_defect("contradiction", "persistent")]

    result = run_repair_loop(
        generated_output="broken",
        judge_defects=[_defect()],
        budget_manager=_budget_mgr(),
        budget=PipelineBudget(),
        repair_fn=repair_fn,
        rejudge_fn=rejudge_fn,
        max_repairs=2,
    )
    assert result.repair_count == 2
    assert result.bypassed is True
    assert "max_repairs=2" in (result.bypass_reason or "")
    assert any("contradiction" in c for c in result.caveats)


# ── circuit-breaker (budget) ──────────────────────────────────────────

def test_circuit_breaker_blocks_repair_when_budget_exhausted() -> None:
    budget = PipelineBudget(total_tokens=100)
    result = run_repair_loop(
        generated_output="broken",
        judge_defects=[_defect()],
        budget_manager=_budget_mgr(),
        budget=budget,
        used_total_tokens=100,  # exhausted
    )
    assert result.bypassed is True
    assert result.repair_count == 0
    assert "exhausted" in (result.bypass_reason or "").lower() or "exceed" in (result.bypass_reason or "").lower()  # noqa: E501
    assert len(result.caveats) >= 1


def test_circuit_breaker_blocks_when_critique_repair_budget_exceeded() -> None:
    budget = PipelineBudget(total_tokens=15000)
    allocations = _budget_mgr().stage_allocations(budget)
    # Spend all of the critique/repair allocation.
    result = run_repair_loop(
        generated_output="broken",
        judge_defects=[_defect()],
        budget_manager=_budget_mgr(),
        budget=budget,
        critique_repair_tokens_spent=allocations["critique_repair"],
    )
    assert result.bypassed is True
    assert result.repair_count == 0


# ── actionable defect coverage ────────────────────────────────────────

@pytest.mark.parametrize("kind", sorted(ACTIONABLE_DEFECTS))
def test_each_actionable_defect_triggers_repair(kind: str) -> None:
    result = run_repair_loop(
        generated_output="broken",
        judge_defects=[Defect(kind=kind, description="test")],
        budget_manager=_budget_mgr(),
        budget=PipelineBudget(),
        repair_fn=lambda o, d: "fixed",
        rejudge_fn=lambda o: [],
    )
    assert result.repaired is True
    assert result.repair_count == 1
