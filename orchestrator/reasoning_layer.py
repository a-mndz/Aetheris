"""Candidate generation with no retrieval or judging."""

from __future__ import annotations

from typing import Any

from core.passport import ExecutionPassport
from core.schemas import AgentOutput
from orchestrator.knowledge_layer import KnowledgeBundle


class ReasoningLayer:
    """Wrap DecisionEngine breaker and generation calls."""

    def __init__(self, decision_engine: Any) -> None:
        self._decision_engine = decision_engine

    async def run_breaker(
        self,
        *,
        knowledge: KnowledgeBundle,
        gateway: Any,
        strategy: Any,
        pool: Any,
        passport: ExecutionPassport,
    ) -> tuple[bool, AgentOutput | None]:
        return await self._decision_engine.execute_breaker_gate(
            query=knowledge.query,
            gateway=gateway,
            strategy=strategy,
            pool=pool,
            passport=passport,
            history=knowledge.reasoning_history(),
        )

    async def generate(
        self,
        *,
        knowledge: KnowledgeBundle,
        gateway: Any,
        strategy: Any,
        pool: Any,
        passport: ExecutionPassport,
    ) -> tuple[AgentOutput | None, AgentOutput | None]:
        return await self._decision_engine.execute_generation_agents(
            query=knowledge.query,
            gateway=gateway,
            strategy=strategy,
            pool=pool,
            passport=passport,
            history=knowledge.reasoning_history(),
        )
