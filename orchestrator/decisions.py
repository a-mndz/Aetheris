"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Decision Engine: Breaker → Logician/Creative → Judge gate architecture.

Implements the core decision flow with precise timing specifications:
- Breaker gate: 100ms timeout, knowledge-absence detection (confidence < 0.3 or sentinel)
- Parallel generation: 30-second timeout for Logician + Creative
- Judge synthesis: validation scoring with placeholder handling for failed agents
- Rolling metrics: breaker_pass_rate, judge_agreement_rate, synthesis_quality_avg
"""

from __future__ import annotations
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from agents.parser import parse_and_repair
from agents.prompt_utils import (
    assemble_breaker_prompt,
    assemble_logician_prompt,
    assemble_creative_prompt,
    safe_parse_agent_output,
)
from api_gateway.rate_limiter import AsyncAPIGateway, ProviderPool
from api_gateway.strategy import ProviderStrategy
from core.passport import ExecutionPassport
from core.schemas import AgentOutput, aetherisOutput
from core.error_handlers import log_and_record_error, log_and_record_warning, execute_with_passport_logging
from orchestrator.evaluation import arbitrate_and_synthesize
from orchestrator.memory import epistemic_memory
from orchestrator.streaming import StreamEvent, EventType

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────


class DecisionStrategy(str, Enum):
    """Decision gate execution strategies."""

    PARALLEL = "parallel"  # Logician and Creative run concurrently
    SEQUENTIAL = "sequential"  # Logician runs first, Creative only if needed
    CONDITIONAL = "conditional"  # Creative only if Logician confidence < 0.7


# ── Metrics Dataclass ───────────────────────────────────────────────────


@dataclass
class DecisionMetrics:
    """Rolling-window metrics for the decision engine."""

    breaker_pass_rate: float = 0.0
    judge_agreement_rate: float = 0.0
    synthesis_quality_avg: float = 0.0
    total_decisions: int = 0


# ── Decision Engine ──────────────────────────────────────────────────────


class DecisionEngine:
    """
    Implements the Decision Gate Architecture: Breaker → Logician/Creative → Judge.

    Timing specifications (from Requirement 9):
    - Breaker timeout: 100ms
    - Knowledge absence threshold: confidence < 0.3 or sentinel string
    - Abort delay: 10ms after absence detection
    - Parallel agent timeout: 30 seconds
    - Conditional threshold: 0.7 (Creative runs only if Logician < 0.7)
    - Judge agreement threshold: validation_score >= 7.0
    - Rolling metrics window: 100 executions
    """

    # ── Timing Constants ─────────────────────────────────────────────
    BREAKER_TIMEOUT_MS: int = 100
    KNOWLEDGE_ABSENCE_THRESHOLD: float = 0.3
    KNOWLEDGE_ABSENCE_SENTINEL: str = "KNOWLEDGE ABSENCE DETECTED"
    ABORT_DELAY_MS: int = 10
    PARALLEL_AGENT_TIMEOUT_SEC: int = 30
    CONDITIONAL_CONFIDENCE_THRESHOLD: float = 0.7
    JUDGE_AGREEMENT_THRESHOLD: float = 7.0
    METRICS_WINDOW_SIZE: int = 100

    def __init__(
        self,
        strategy: DecisionStrategy = DecisionStrategy.PARALLEL,
        streaming_manager: Any = None,
    ) -> None:
        self.strategy = strategy
        self.metrics = DecisionMetrics()
        self.streaming_manager = streaming_manager

        # Rolling-window deques (maxlen=100)
        self._breaker_history: deque[bool] = deque(maxlen=self.METRICS_WINDOW_SIZE)
        self._judge_history: deque[bool] = deque(maxlen=self.METRICS_WINDOW_SIZE)
        self._synthesis_scores: deque[float] = deque(maxlen=self.METRICS_WINDOW_SIZE)

    # ── Public API ───────────────────────────────────────────────────

    async def execute_breaker_gate(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[bool, AgentOutput | None]:
        """
        Execute the Breaker gate within 100ms.

        Returns ``(should_continue, breaker_output)``.

        Knowledge absence is detected when:
        - ``breaker_output.confidence < 0.3``, OR
        - ``breaker_output.answer`` contains the sentinel string
          ``"KNOWLEDGE ABSENCE DETECTED"``.

        On timeout: returns ``(False, None)`` and records an error.
        """
        try:
            breaker_output = await asyncio.wait_for(
                self._execute_breaker(query, gateway, strategy, pool, passport, history),
                timeout=self.BREAKER_TIMEOUT_MS / 1000.0,
            )
        except asyncio.TimeoutError:
            passport.record_error(
                "breaker",
                f"Breaker execution timeout exceeded {self.BREAKER_TIMEOUT_MS}ms",
            )
            self._breaker_history.append(False)
            logger.warning("Breaker gate timed out after %dms", self.BREAKER_TIMEOUT_MS)
            return False, None
        except Exception as exc:
            log_and_record_error(passport, "breaker", exc, logger_instance=logger)
            self._breaker_history.append(False)
            return False, None

        is_absent = (
            breaker_output.confidence < self.KNOWLEDGE_ABSENCE_THRESHOLD
            or self.KNOWLEDGE_ABSENCE_SENTINEL in breaker_output.answer
        )

        should_continue = not is_absent
        self._breaker_history.append(should_continue)

        if is_absent:
            logger.warning(
                "Breaker detected knowledge absence (confidence=%.2f, sentinel=%s)",
                breaker_output.confidence,
                self.KNOWLEDGE_ABSENCE_SENTINEL in breaker_output.answer,
                extra={"stage": "breaker", "confidence": breaker_output.confidence, "absent": True}
            )
            if self.streaming_manager:
                asyncio.create_task(self.streaming_manager.emit_event(
                    request_id=passport.request_id,
                    event=StreamEvent(
                        event=EventType.BREAKER_FAILED,
                        data={"confidence": breaker_output.confidence}
                    )
                ))
        else:
            logger.info(
                "Breaker gate passed (confidence=%.2f).",
                breaker_output.confidence,
                extra={"stage": "breaker", "confidence": breaker_output.confidence, "absent": False}
            )
            if self.streaming_manager:
                asyncio.create_task(self.streaming_manager.emit_event(
                    request_id=passport.request_id,
                    event=StreamEvent(
                        event=EventType.BREAKER_PASSED,
                        data={"confidence": breaker_output.confidence}
                    )
                ))

        return should_continue, breaker_output

    async def execute_generation_agents(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[Optional[AgentOutput], Optional[AgentOutput]]:
        """
        Execute Logician and Creative agents within 30 seconds.

        Returns ``(logician_output, creative_output)`` where ``None``
        indicates a failed agent.

        Partial failures are handled:
        - One agent fails: warning recorded, the other's output is used.
        - Both fail: error recorded, both return ``None``.
        """
        if self.strategy == DecisionStrategy.SEQUENTIAL:
            res = await self._execute_sequential(query, gateway, strategy, pool, passport, history)
        elif self.strategy == DecisionStrategy.CONDITIONAL:
            res = await self._execute_conditional(query, gateway, strategy, pool, passport, history)
        else:
            # Default: PARALLEL
            res = await self._execute_parallel(query, gateway, strategy, pool, passport, history)
        
        if self.streaming_manager:
            asyncio.create_task(self.streaming_manager.emit_event(
                request_id=passport.request_id,
                event=StreamEvent(
                    event=EventType.GENERATION_COMPLETED,
                    data={"strategy": self.strategy.value}
                )
            ))
        return res

    async def execute_judge_synthesis(
        self,
        query: str,
        logician_output: Optional[AgentOutput],
        creative_output: Optional[AgentOutput],
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        lessons: str = "",
        history: list[dict[str, str]] | None = None,
    ) -> aetherisOutput:
        """
        Execute the Judge agent to synthesize outputs.

        Failed agents receive placeholders with ``confidence=0.0``.
        Tracks ``_judge_history`` and ``_synthesis_scores``.
        """
        if logician_output is None:
            logician_output = AgentOutput(
                reasoning_steps=["[Agent execution failed]"],
                answer="[Logician output unavailable due to execution failure]",
                confidence=0.0,
            )
        if creative_output is None:
            creative_output = AgentOutput(
                reasoning_steps=["[Agent execution failed]"],
                answer="[Creative output unavailable due to execution failure]",
                confidence=0.0,
            )

        judge_output = await arbitrate_and_synthesize(
            query=query,
            answer_a=logician_output.answer,
            answer_b=creative_output.answer,
            gateway=gateway,
            strategy=strategy,
            pool=pool,
            lessons=lessons,
            history=history,
        )

        if isinstance(judge_output, dict):
            # Parse failure — wrap in a safe aetherisOutput
            logger.error("Judge returned raw dict, wrapping: %s", judge_output)
            judge_output = aetherisOutput(
                final_answer=judge_output.get("final_answer", "Judge synthesis failed"),
                overall_confidence="Low",
                overall_bias_risk="High",
                disagreement_notes=["Judge output was not a valid aetherisOutput"],
                validation_score=0.0,
            )

        # Track metrics
        self._judge_history.append(
            judge_output.validation_score >= self.JUDGE_AGREEMENT_THRESHOLD
        )
        self._synthesis_scores.append(judge_output.validation_score)

        logger.info(
            "Judge synthesis complete — validation_score=%.2f, confidence=%s",
            judge_output.validation_score,
            judge_output.overall_confidence,
            extra={"stage": "judge", "score": judge_output.validation_score, "confidence": judge_output.overall_confidence}
        )

        if self.streaming_manager:
            asyncio.create_task(self.streaming_manager.emit_event(
                request_id=passport.request_id,
                event=StreamEvent(
                    event=EventType.JUDGE_SYNTHESIZED,
                    data={"score": judge_output.validation_score, "confidence": judge_output.overall_confidence}
                )
            ))

        return judge_output

    def update_metrics(self) -> None:
        """Recalculate metrics from the rolling windows."""
        if len(self._breaker_history) > 0:
            self.metrics.breaker_pass_rate = (
                sum(self._breaker_history) / len(self._breaker_history)
            )
        if len(self._judge_history) > 0:
            self.metrics.judge_agreement_rate = (
                sum(self._judge_history) / len(self._judge_history)
            )
        if len(self._synthesis_scores) > 0:
            self.metrics.synthesis_quality_avg = (
                sum(self._synthesis_scores) / len(self._synthesis_scores)
            )
        self.metrics.total_decisions = len(self._breaker_history)

    def get_metrics(self) -> DecisionMetrics:
        """Return current decision metrics calculated over rolling window."""
        self.update_metrics()
        return self.metrics

    # ── Private: Agent Execution Wrappers ────────────────────────────

    async def _execute_breaker(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> AgentOutput:
        """Assemble Breaker prompt, call gateway, parse into AgentOutput."""
        passport.update_stage("breaker")
        system_prompt = assemble_breaker_prompt(strategy.mode.value)
        raw = await gateway.execute_with_fallback(
            prompt=query,
            system_prompt=system_prompt,
            role="breaker",
            strategy=strategy,
            pool=pool,
            history=history,
        )
        return safe_parse_agent_output(raw, "Breaker", parse_and_repair, AgentOutput)

    async def _execute_logician(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> AgentOutput:
        """Assemble Logician prompt, call gateway, parse into AgentOutput."""
        system_prompt = assemble_logician_prompt(strategy.mode.value)
        raw = await gateway.execute_with_fallback(
            prompt=query,
            system_prompt=system_prompt,
            role="generation",
            strategy=strategy,
            pool=pool,
            history=history,
        )
        return safe_parse_agent_output(raw, "Logician", parse_and_repair, AgentOutput)

    async def _execute_creative(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> AgentOutput:
        """Assemble Creative prompt, call gateway, parse into AgentOutput."""
        system_prompt = assemble_creative_prompt(strategy.mode.value)
        raw = await gateway.execute_with_fallback(
            prompt=query,
            system_prompt=system_prompt,
            role="generation",
            strategy=strategy,
            pool=pool,
            history=history,
        )
        return safe_parse_agent_output(raw, "Creative", parse_and_repair, AgentOutput)

    # ── Private: Execution Strategies ────────────────────────────────

    async def _execute_parallel(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[Optional[AgentOutput], Optional[AgentOutput]]:
        """Execute Logician and Creative in parallel with 30-second timeout."""
        logician_task = self._execute_logician(query, gateway, strategy, pool, passport, history)
        creative_task = self._execute_creative(query, gateway, strategy, pool, passport, history)

        try:
            results = await asyncio.wait_for(
                asyncio.gather(logician_task, creative_task, return_exceptions=True),
                timeout=self.PARALLEL_AGENT_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            passport.record_error(
                "generation",
                f"Parallel agent execution timeout exceeded {self.PARALLEL_AGENT_TIMEOUT_SEC}s",
            )
            logger.error(
                "Parallel execution timed out after %ds", self.PARALLEL_AGENT_TIMEOUT_SEC
            )
            return None, None

        logician_output: Optional[AgentOutput] = None
        creative_output: Optional[AgentOutput] = None

        # Unpack results — exceptions become None
        for idx, result in enumerate(results):
            if isinstance(result, BaseException):
                name = "Logician" if idx == 0 else "Creative"
                logger.error("%s generation failed: %s", name, result)
            else:
                if idx == 0:
                    logician_output = result
                else:
                    creative_output = result

        # Handle partial failures
        if logician_output is None and creative_output is not None:
            passport.record_warning("Logician agent failed but Creative succeeded")
            logger.warning("Logician failed; using Creative output only.")
        elif creative_output is None and logician_output is not None:
            passport.record_warning("Creative agent failed but Logician succeeded")
            logger.warning("Creative failed; using Logician output only.")
        elif logician_output is None and creative_output is None:
            passport.record_error("generation", "Both Logician and Creative agents failed")
            logger.error("Both generation agents failed.")

        return logician_output, creative_output

    async def _execute_sequential(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[Optional[AgentOutput], Optional[AgentOutput]]:
        """Execute Logician first, then Creative only if needed."""
        logician_output = await execute_with_passport_logging(
            self._execute_logician(query, gateway, strategy, pool, passport, history),
            passport,
            "generation",
            "Sequential Logician",
            logger_instance=logger,
        )
        if logician_output is None:
            return None, None

        creative_output = await execute_with_passport_logging(
            self._execute_creative(query, gateway, strategy, pool, passport, history),
            passport,
            "generation",
            "Sequential Creative",
            logger_instance=logger,
            on_error_return=None,
        )

        return logician_output, creative_output

    async def _execute_conditional(
        self,
        query: str,
        gateway: AsyncAPIGateway,
        strategy: ProviderStrategy,
        pool: ProviderPool,
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[Optional[AgentOutput], Optional[AgentOutput]]:
        """Run Logician first; if confidence < 0.7, also run Creative."""
        logician_output = await execute_with_passport_logging(
            self._execute_logician(query, gateway, strategy, pool, passport, history),
            passport,
            "generation",
            "Conditional Logician",
            logger_instance=logger,
        )
        if logician_output is None:
            return None, None

        if logician_output.confidence >= self.CONDITIONAL_CONFIDENCE_THRESHOLD:
            logger.info(
                "Logician confidence %.2f >= %.2f — skipping Creative.",
                logician_output.confidence,
                self.CONDITIONAL_CONFIDENCE_THRESHOLD,
            )
            return logician_output, None

        logger.info(
            "Logician confidence %.2f < %.2f — executing Creative.",
            logician_output.confidence,
            self.CONDITIONAL_CONFIDENCE_THRESHOLD,
        )
        creative_output = await execute_with_passport_logging(
            self._execute_creative(query, gateway, strategy, pool, passport, history),
            passport,
            "generation",
            "Conditional Creative",
            logger_instance=logger,
            on_error_return=None,
        )

        return logician_output, creative_output
