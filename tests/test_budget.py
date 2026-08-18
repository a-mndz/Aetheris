from __future__ import annotations

from core.runtime import RuntimeContract
from orchestrator.budget import TokenBudgetManager
from orchestrator.memory_manager import MemoryManager


def _messages(count: int, *, words_per_message: int = 30) -> list[dict[str, str]]:
    content = " ".join(f"word{i}" for i in range(words_per_message))
    return [{"role": "user", "content": content} for _ in range(count)]


def test_budget_manager_defaults_and_allocations_sum_to_total() -> None:
    manager = TokenBudgetManager(runtime_contract=RuntimeContract(max_tokens=20_000))

    budget = manager.create_budget()
    allocations = manager.stage_allocations(budget)

    assert budget.total_tokens == 15_000
    assert allocations == {
        "planning": 750,
        "generation": 6750,
        "critique_repair": 3000,
        "judge": 2250,
        "memory": 1500,
        "final": 750,
    }


def test_budget_manager_compresses_history_when_pressure_is_tight() -> None:
    manager = TokenBudgetManager(memory_manager=MemoryManager())
    budget = manager.create_budget(requested_total_tokens=100)
    messages = _messages(8, words_per_message=20)

    result = manager.maybe_compress_history(messages, budget=budget, reserved_tokens=5)

    assert result.applied is True
    assert result.pressure in {"tight", "critical", "exhausted"}
    assert result.messages != messages


def test_budget_manager_blocks_repair_when_critique_budget_is_exhausted() -> None:
    manager = TokenBudgetManager()
    budget = manager.create_budget()

    decision = manager.evaluate_repair_cycle(
        budget=budget,
        estimated_repair_tokens=400,
        critique_repair_tokens_spent=2800,
        used_total_tokens=10_000,
    )

    assert decision.allowed is False
    assert "critique / repair budget" in decision.reason


def test_budget_manager_honors_tighter_runtime_contract() -> None:
    manager = TokenBudgetManager(runtime_contract=RuntimeContract(max_tokens=2048))

    budget = manager.create_budget()

    assert budget.total_tokens == 2048
