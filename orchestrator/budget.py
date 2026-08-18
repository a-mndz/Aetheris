"""Token budget management for the DAG runtime."""

from __future__ import annotations

from dataclasses import dataclass

from core.runtime import RuntimeContract
from core.schemas import PipelineBudget
from orchestrator.memory_manager import MemoryManager, SummarizationStrategy


@dataclass(frozen=True)
class BudgetSnapshot:
    """Point-in-time view of budget usage and pressure."""

    budget: PipelineBudget
    stage_allocations: dict[str, int]
    used_tokens: int
    remaining_tokens: int
    pressure: str


@dataclass(frozen=True)
class BudgetCompressionResult:
    """Result of applying history compression under budget pressure."""

    messages: list[dict[str, str]]
    summary: str | None
    applied: bool
    pressure: str
    strategy: str | None = None


@dataclass(frozen=True)
class RepairBudgetDecision:
    """Decision on whether a repair cycle is allowed to run."""

    allowed: bool
    reason: str
    remaining_critique_repair_tokens: int
    estimated_repair_tokens: int
    pressure: str


class TokenBudgetManager:
    """Own the token budget and pressure transitions for a request."""

    DEFAULT_TOTAL_TOKENS = 15_000
    _PRESSURE_NORMAL_THRESHOLD = 0.80
    _PRESSURE_CRITICAL_THRESHOLD = 0.90

    def __init__(
        self,
        *,
        memory_manager: MemoryManager | None = None,
        runtime_contract: RuntimeContract | None = None,
    ) -> None:
        self._memory_manager = memory_manager or MemoryManager()
        self._runtime_contract = runtime_contract

    def create_budget(self, *, requested_total_tokens: int | None = None) -> PipelineBudget:
        """Create the effective budget, honoring any tighter runtime contract."""

        effective_total = self.DEFAULT_TOTAL_TOKENS
        if requested_total_tokens is not None:
            effective_total = min(effective_total, max(1, requested_total_tokens))
        if self._runtime_contract is not None:
            effective_total = min(effective_total, max(1, self._runtime_contract.max_tokens))
        return PipelineBudget(total_tokens=effective_total)

    def stage_allocations(self, budget: PipelineBudget) -> dict[str, int]:
        """Expand percentage splits into integer token buckets."""

        allocations = {
            "planning": int(budget.total_tokens * (budget.planning_pct / 100.0)),
            "generation": int(budget.total_tokens * (budget.generation_pct / 100.0)),
            "critique_repair": int(budget.total_tokens * (budget.critique_repair_pct / 100.0)),
            "judge": int(budget.total_tokens * (budget.judge_pct / 100.0)),
            "memory": int(budget.total_tokens * (budget.memory_pct / 100.0)),
        }
        allocations["final"] = max(0, budget.total_tokens - sum(allocations.values()))
        return allocations

    def count_history_tokens(self, messages: list[dict[str, str]] | None) -> int:
        if not messages:
            return 0
        return self._memory_manager.track_tokens(messages)

    def pressure_for_usage(self, used_tokens: int, budget: PipelineBudget) -> str:
        """Map current token usage to a pressure state."""

        if budget.total_tokens <= 0:
            return "exhausted"
        utilization = used_tokens / budget.total_tokens
        if utilization >= 1.0:
            return "exhausted"
        if utilization >= self._PRESSURE_CRITICAL_THRESHOLD:
            return "critical"
        if utilization >= self._PRESSURE_NORMAL_THRESHOLD:
            return "tight"
        return "normal"

    def snapshot(
        self,
        *,
        budget: PipelineBudget,
        used_tokens: int = 0,
        messages: list[dict[str, str]] | None = None,
    ) -> BudgetSnapshot:
        """Build a consistent budget snapshot for telemetry and decisions."""

        total_used = used_tokens + self.count_history_tokens(messages)
        pressure = self.pressure_for_usage(total_used, budget)
        budget.pressure = pressure
        return BudgetSnapshot(
            budget=budget,
            stage_allocations=self.stage_allocations(budget),
            used_tokens=total_used,
            remaining_tokens=max(0, budget.total_tokens - total_used),
            pressure=pressure,
        )

    def maybe_compress_history(
        self,
        messages: list[dict[str, str]] | None,
        *,
        budget: PipelineBudget,
        reserved_tokens: int = 0,
    ) -> BudgetCompressionResult:
        """Compress history when pressure moves beyond the normal state."""

        if not messages:
            return BudgetCompressionResult(
                messages=[],
                summary=None,
                applied=False,
                pressure=self.pressure_for_usage(reserved_tokens, budget),
            )

        history_tokens = self.count_history_tokens(messages)
        pressure = self.pressure_for_usage(history_tokens + reserved_tokens, budget)
        if pressure == "normal":
            return BudgetCompressionResult(
                messages=list(messages),
                summary=None,
                applied=False,
                pressure=pressure,
            )

        strategy = (
            SummarizationStrategy.SEMANTIC_COMPRESSION
            if pressure == "tight"
            else SummarizationStrategy.HIERARCHICAL
        )
        compressed_messages, summary = self._memory_manager.compress_history(
            messages,
            strategy=strategy,
            max_limit=budget.total_tokens,
        )
        return BudgetCompressionResult(
            messages=compressed_messages,
            summary=summary,
            applied=True,
            pressure=pressure,
            strategy=strategy.value,
        )

    def evaluate_repair_cycle(
        self,
        *,
        budget: PipelineBudget,
        estimated_repair_tokens: int,
        critique_repair_tokens_spent: int = 0,
        used_total_tokens: int = 0,
    ) -> RepairBudgetDecision:
        """Treat the budget as the repair circuit breaker."""

        allocations = self.stage_allocations(budget)
        remaining_critique = max(
            0,
            allocations["critique_repair"] - critique_repair_tokens_spent,
        )
        pressure = self.pressure_for_usage(used_total_tokens, budget)

        if pressure == "exhausted":
            return RepairBudgetDecision(
                allowed=False,
                reason="budget exhausted; synthesize from verified state",
                remaining_critique_repair_tokens=remaining_critique,
                estimated_repair_tokens=estimated_repair_tokens,
                pressure=pressure,
            )
        if estimated_repair_tokens > remaining_critique:
            return RepairBudgetDecision(
                allowed=False,
                reason="repair would exceed the critique / repair budget",
                remaining_critique_repair_tokens=remaining_critique,
                estimated_repair_tokens=estimated_repair_tokens,
                pressure=pressure,
            )
        if used_total_tokens + estimated_repair_tokens > budget.total_tokens:
            return RepairBudgetDecision(
                allowed=False,
                reason="repair would exceed the total token budget",
                remaining_critique_repair_tokens=remaining_critique,
                estimated_repair_tokens=estimated_repair_tokens,
                pressure=pressure,
            )
        return RepairBudgetDecision(
            allowed=True,
            reason="repair budget available",
            remaining_critique_repair_tokens=remaining_critique,
            estimated_repair_tokens=estimated_repair_tokens,
            pressure=pressure,
        )
