"""
aetheris — Pipeline Scheduler with State Machine Integration

Orchestrates pipeline execution stages with state machine enforcement,
checkpoint creation, parallel agent execution, and fallback handling.

Specifications from Requirements 4, 14, 13:
- Pipeline stages: Normalize, Breach_Check, Generation, Evaluation, Synthesis, Formatting
- State machine integration with valid transition enforcement
- Checkpoint creation after each major stage (5s save timeout)
- Parallel agent execution with fallback logic
- Telemetry event emission for stage transitions
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Optional

from core.passport import ExecutionPassport
from core.error_handlers import log_and_record_error, log_and_record_warning
from orchestrator.state_machine import InvalidTransitionError, PipelineState, StateMachine
from orchestrator.checkpoints import CheckpointManager
from orchestrator.streaming import EventType, StreamingManager, StreamEvent

logger = logging.getLogger(__name__)


# ── Pipeline Stage Enum ──────────────────────────────────────────────────


class PipelineStage(str, Enum):
    """Pipeline execution stages matching StateMachine states."""

    NORMALIZE = "normalize"
    BREACH_CHECK = "breach_check"
    GENERATION = "generation"
    EVALUATION = "evaluation"
    SYNTHESIS = "synthesis"
    FORMATTING = "formatting"


# Mapping from PipelineStage to PipelineState for state machine transitions
_STAGE_TO_STATE: dict[PipelineStage, PipelineState] = {
    PipelineStage.NORMALIZE: PipelineState.NORMALIZING,
    PipelineStage.BREACH_CHECK: PipelineState.BREACH_CHECKING,
    PipelineStage.GENERATION: PipelineState.GENERATING,
    PipelineStage.EVALUATION: PipelineState.EVALUATING,
    PipelineStage.SYNTHESIS: PipelineState.SYNTHESIZING,
    PipelineStage.FORMATTING: PipelineState.FORMATTING,
}

# Ordered pipeline stages for sequential execution
_PIPELINE_ORDER: list[PipelineStage] = [
    PipelineStage.NORMALIZE,
    PipelineStage.BREACH_CHECK,
    PipelineStage.GENERATION,
    PipelineStage.EVALUATION,
    PipelineStage.SYNTHESIS,
    PipelineStage.FORMATTING,
]


# ── Pipeline Scheduler ───────────────────────────────────────────────────


class PipelineScheduler:
    """
    Orchestrates pipeline execution stages with state machine enforcement,
    checkpoint creation, parallel agent execution, and fallback handling.

    Requirements:
    - Uses StateMachine for valid transition enforcement (Req 14)
    - Creates Checkpoints after each major stage (Req 13)
    - Supports parallel agent execution (Req 4.3)
    - Implements fallback logic for stage failures (Req 4.4)
    - Emits telemetry events for stage transitions (Req 4.5)
    """

    def __init__(
        self,
        state_machine: StateMachine,
        checkpoint_mgr: CheckpointManager,
        streaming_mgr: Optional[StreamingManager] = None,
    ) -> None:
        """
        Initialize the PipelineScheduler.

        Args:
            state_machine: State machine for transition enforcement.
            checkpoint_mgr: Checkpoint manager for state persistence.
            streaming_mgr: Optional streaming manager for telemetry events.
        """
        self.state_machine = state_machine
        self.checkpoint_mgr = checkpoint_mgr
        self.streaming_mgr = streaming_mgr
        logger.info(
            "PipelineScheduler initialized (request=%s)",
            state_machine.request_id,
        )

    # ── Pipeline Execution ───────────────────────────────────────────

    async def execute_pipeline(
        self,
        user_query: str,
        stage_handlers: dict[PipelineStage, Callable[..., Any]],
        passport: ExecutionPassport,
        history: list[dict[str, str]] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the complete pipeline through all stages with state transitions
        and checkpoint creation.

        Args:
            user_query: The original user query.
            stage_handlers: Dict mapping PipelineStage to async handler functions.
                Each handler receives (context, passport) and returns stage result.
            passport: Execution passport for request tracking.
            history: Optional conversation history.
            session_id: Optional session identifier for checkpoints.

        Returns:
            Dict with pipeline result including status, final output, and metadata.
        """
        request_id = passport.request_id
        context: dict[str, Any] = {
            "user_query": user_query,
            "history": history or [],
            "session_id": session_id,
            "request_id": request_id,
            "results": {},
        }

        logger.info(
            "Pipeline execution started for request=%s, query=%.120s",
            request_id,
            user_query,
        )

        for stage in _PIPELINE_ORDER:
            if stage not in stage_handlers:
                logger.warning(
                    "No handler registered for stage %s, skipping", stage.value
                )
                # Still advance the state machine through skipped stages
                target_state = _STAGE_TO_STATE.get(stage)
                if target_state is not None and self.state_machine.can_transition(target_state):
                    try:
                        self.state_machine.transition(
                            target_state,
                            metadata={"request_id": request_id, "stage": stage.value, "skipped": True},
                        )
                    except InvalidTransitionError:
                        pass
                continue

            result = await self.execute_stage(
                stage=stage,
                handler=stage_handlers[stage],
                context=context,
                passport=passport,
                session_id=session_id,
            )

            if result is None:
                # Stage failed and no fallback available — pipeline aborted
                logger.warning(
                    "Pipeline aborted at stage %s for request=%s",
                    stage.value,
                    request_id,
                )
                return {
                    "status": "failed",
                    "request_id": request_id,
                    "failed_stage": stage.value,
                    "results": context["results"],
                }

            context["results"][stage.value] = result

        # All stages completed — transition to COMPLETED
        try:
            self.state_machine.transition(
                PipelineState.COMPLETED,
                metadata={"request_id": request_id},
            )
        except InvalidTransitionError as exc:
            logger.error(
                "Failed to transition to COMPLETED for request=%s: %s",
                request_id,
                exc,
            )

        # Create final checkpoint
        await self._create_checkpoint(
            request_id=request_id,
            session_id=session_id,
            stage="completed",
            agent_outputs=context["results"],
            partial_results={},
            passport=passport,
        )

        logger.info(
            "Pipeline execution completed successfully for request=%s", request_id
        )

        return {
            "status": "success",
            "request_id": request_id,
            "results": context["results"],
        }

    # ── Stage Execution ──────────────────────────────────────────────

    async def execute_stage(
        self,
        stage: PipelineStage,
        handler: Callable[..., Any],
        context: dict[str, Any],
        passport: ExecutionPassport,
        session_id: str | None = None,
    ) -> Any:
        """
        Execute a single pipeline stage with state transition, error handling,
        and checkpoint creation.

        Args:
            stage: The pipeline stage to execute.
            handler: Async callable that executes the stage logic.
                Receives (context, passport) and returns stage result.
            context: Pipeline context dict shared across stages.
            passport: Execution passport for request tracking.
            session_id: Optional session identifier for checkpoints.

        Returns:
            Stage result on success, None on failure (after fallback attempt).
        """
        request_id = passport.request_id
        target_state = _STAGE_TO_STATE.get(stage)

        # Transition state machine
        if target_state is not None:
            if self.state_machine.current_state == target_state:
                # Already at target state — no transition needed
                pass
            elif self.state_machine.can_transition(target_state):
                try:
                    self.state_machine.transition(
                        target_state,
                        metadata={"request_id": request_id, "stage": stage.value},
                    )
                except InvalidTransitionError as exc:
                    logger.error(
                        "Invalid state transition to %s for request=%s: %s",
                        target_state.value,
                        request_id,
                        exc,
                    )
                    passport.record_error(stage.value, f"Invalid transition: {exc}")
                    return None
            else:
                logger.error(
                    "Cannot transition from %s to %s for request=%s",
                    self.state_machine.current_state.value,
                    target_state.value,
                    request_id,
                )
                passport.record_error(
                    stage.value,
                    f"Cannot transition from {self.state_machine.current_state.value} to {target_state.value}",
                )
                return None

        # Update passport stage
        passport.update_stage(stage.value)

        # Emit stage transition event
        self.emit_stage_transition(stage, passport)

        # Execute stage logic
        try:
            result = await handler(context, passport)
        except Exception as exc:
            log_and_record_error(
                passport, stage.value, exc, logger_instance=logger
            )
            return await self.handle_stage_failure(stage, exc, passport)

        # Stage succeeded — create checkpoint
        await self._create_checkpoint(
            request_id=request_id,
            session_id=session_id,
            stage=stage.value,
            agent_outputs={stage.value: result},
            partial_results=context.get("results", {}),
            passport=passport,
        )

        logger.info(
            "Stage %s completed for request=%s", stage.value, request_id
        )
        return result

    # ── Parallel Agent Execution ─────────────────────────────────────

    async def execute_parallel_agents(
        self,
        agents: dict[str, Callable[..., Any]],
        context: dict[str, Any],
        passport: ExecutionPassport,
    ) -> dict[str, Any | None]:
        """
        Execute multiple agents in parallel and collect results.

        Args:
            agents: Dict mapping agent names to async handler functions.
                Each handler receives (context, passport) and returns agent output.
            context: Pipeline context dict shared across stages.
            passport: Execution passport for request tracking.

        Returns:
            Dict mapping agent names to their outputs (None for failed agents).
        """
        request_id = passport.request_id
        logger.info(
            "Executing %d agents in parallel for request=%s: %s",
            len(agents),
            request_id,
            list(agents.keys()),
        )

        async def _run_agent(name: str, handler: Callable) -> tuple[str, Any | None]:
            try:
                result = await handler(context, passport)
                return name, result
            except Exception as exc:
                log_and_record_error(
                    passport,
                    f"agent_{name}",
                    exc,
                    details={"agent": name},
                    logger_instance=logger,
                )
                return name, None

        tasks = [
            _run_agent(name, handler) for name, handler in agents.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        agent_outputs: dict[str, Any | None] = {}
        for result in results:
            if isinstance(result, BaseException):
                logger.error(
                    "Unexpected agent task exception for request=%s: %s",
                    request_id,
                    result,
                )
                continue
            name, output = result
            agent_outputs[name] = output

        # Log summary
        failed_agents = [n for n, o in agent_outputs.items() if o is None]
        if failed_agents:
            logger.warning(
                "Failed agents for request=%s: %s",
                request_id,
                failed_agents,
            )
        else:
            logger.info(
                "All %d agents completed successfully for request=%s",
                len(agents),
                request_id,
            )

        return agent_outputs

    # ── Stage Failure Handling ───────────────────────────────────────

    async def handle_stage_failure(
        self,
        stage: PipelineStage,
        error: Exception,
        passport: ExecutionPassport,
        fallback_handler: Callable[..., Any] | None = None,
    ) -> Any:
        """
        Handle a stage failure by recording the error, attempting fallback
        if available, or transitioning to FAILED state.

        Args:
            stage: The stage that failed.
            error: The exception that occurred.
            passport: Execution passport for request tracking.
            fallback_handler: Optional async fallback handler.
                Receives (context, passport) and returns fallback result.

        Returns:
            Fallback result if available and successful, None otherwise.
        """
        request_id = passport.request_id
        error_msg = f"{type(error).__name__}: {error}"

        # Record error in passport
        log_and_record_error(passport, stage.value, error, logger_instance=logger)

        # Emit error event
        if self.streaming_mgr is not None:
            try:
                await self.streaming_mgr.emit(
                    request_id,
                    EventType.ERROR,
                    {
                        "stage": stage.value,
                        "agent": stage.value,
                        "message": error_msg,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Failed to emit error event for request=%s: %s",
                    request_id,
                    exc,
                )

        # Attempt fallback if available
        if fallback_handler is not None:
            logger.info(
                "Attempting fallback for stage %s, request=%s",
                stage.value,
                request_id,
            )
            try:
                context = {"user_query": "", "history": [], "results": {}}
                result = await fallback_handler(context, passport)
                logger.info(
                    "Fallback succeeded for stage %s, request=%s",
                    stage.value,
                    request_id,
                )
                return result
            except Exception as fallback_error:
                logger.error(
                    "Fallback also failed for stage %s, request=%s: %s",
                    stage.value,
                    request_id,
                    fallback_error,
                )
                passport.record_error(
                    stage.value,
                    f"Fallback failed: {type(fallback_error).__name__}: {fallback_error}",
                )

        # No fallback available — transition to FAILED
        try:
            self.state_machine.transition(
                PipelineState.FAILED,
                metadata={
                    "request_id": request_id,
                    "stage": stage.value,
                    "error": error_msg,
                },
            )
        except InvalidTransitionError as exc:
            logger.error(
                "Failed to transition to FAILED for request=%s: %s",
                request_id,
                exc,
            )

        return None

    # ── Telemetry Events ─────────────────────────────────────────────

    def emit_stage_transition(
        self,
        stage: PipelineStage,
        passport: ExecutionPassport,
    ) -> None:
        """
        Emit a telemetry event for a stage transition.

        Args:
            stage: The pipeline stage being entered.
            passport: Execution passport for request tracking.
        """
        target_state = _STAGE_TO_STATE.get(stage)
        if target_state is None:
            return

        # Emit via state machine's transition event
        if not self.state_machine.history:
            return {
                "event": "stage_transition",
                "request_id": passport.request_id,
                "stage": stage.value,
                "state": target_state.value,
                "timestamp": "",
                "metadata": {},
            }

        transition = self.state_machine.emit_transition_event(
            self.state_machine.history[-1]
        )

        event_data = {
            "event": "stage_transition",
            "request_id": passport.request_id,
            "stage": stage.value,
            "state": target_state.value,
            "timestamp": transition.get("timestamp", ""),
            "metadata": transition.get("metadata", {}),
        }

        logger.info(
            "Stage transition event: %s (state=%s) for request=%s",
            stage.value,
            target_state.value,
            passport.request_id,
        )

        return event_data

    # ── Checkpoint Creation ──────────────────────────────────────────

    async def _create_checkpoint(
        self,
        request_id: str,
        session_id: str | None,
        stage: str,
        agent_outputs: dict[str, Any],
        partial_results: dict[str, Any],
        passport: ExecutionPassport,
    ) -> str | None:
        """
        Create a checkpoint after a successful stage completion.

        Checkpoint creation is best-effort: failures are logged but do not
        block pipeline execution.

        Args:
            request_id: The request identifier.
            session_id: Optional session identifier.
            stage: The stage that just completed.
            agent_outputs: Agent outputs to checkpoint.
            partial_results: Partial pipeline results.
            passport: Execution passport for recording checkpoint ID.

        Returns:
            Checkpoint ID on success, None on failure.
        """
        try:
            checkpoint_id = await self.checkpoint_mgr.save_checkpoint(
                request_id=request_id,
                session_id=session_id,
                stage=stage,
                agent_outputs=agent_outputs,
                partial_results=partial_results,
            )
            passport.add_checkpoint(checkpoint_id)
            logger.info(
                "Checkpoint %s created for stage %s, request=%s",
                checkpoint_id,
                stage,
                request_id,
            )
            return checkpoint_id
        except Exception as exc:
            # Checkpoint failure should not block pipeline
            log_and_record_error(
                passport,
                f"checkpoint.{stage}",
                exc,
                logger_instance=logger,
            )
            return None

    # ── Checkpoint Restoration ───────────────────────────────────────

    async def restore_from_checkpoint(
        self,
        checkpoint_id: str,
        stage_handlers: dict[PipelineStage, Callable[..., Any]],
        passport: ExecutionPassport,
    ) -> dict[str, Any] | None:
        """
        Restore pipeline state from a checkpoint and resume execution.

        Args:
            checkpoint_id: The checkpoint to restore from.
            stage_handlers: Dict mapping PipelineStage to async handler functions.
            passport: Execution passport for request tracking.

        Returns:
            Restored context dict on success, None on failure.
        """
        checkpoint = await self.checkpoint_mgr.restore_checkpoint(checkpoint_id)
        if checkpoint is None:
            logger.error(
                "Failed to restore checkpoint %s for request=%s",
                checkpoint_id,
                passport.request_id,
            )
            return None

        logger.info(
            "Restored checkpoint %s (stage=%s) for request=%s",
            checkpoint_id,
            checkpoint.stage,
            passport.request_id,
        )

        # Reconstruct context from checkpoint
        context: dict[str, Any] = {
            "user_query": "",
            "history": [],
            "session_id": checkpoint.session_id,
            "request_id": checkpoint.request_id,
            "results": {**checkpoint.partial_results, **checkpoint.agent_outputs},
        }

        # Find the stage after the checkpoint's stage
        try:
            checkpoint_stage = PipelineStage(checkpoint.stage)
            stage_index = _PIPELINE_ORDER.index(checkpoint_stage)
            remaining_stages = _PIPELINE_ORDER[stage_index + 1:]
        except (ValueError, IndexError):
            logger.error(
                "Unknown checkpoint stage %s for request=%s",
                checkpoint.stage,
                passport.request_id,
            )
            return None

        # Advance the state machine to the checkpoint's state
        checkpoint_state = _STAGE_TO_STATE.get(checkpoint_stage)
        if checkpoint_state is not None:
            # Navigate through all states up to and including the checkpoint state
            for ps in _PIPELINE_ORDER:
                ps_state = _STAGE_TO_STATE.get(ps)
                if ps_state is None:
                    continue
                if self.state_machine.can_transition(ps_state):
                    try:
                        self.state_machine.transition(
                            ps_state,
                            metadata={"request_id": passport.request_id, "stage": ps.value, "restored": True},
                        )
                    except InvalidTransitionError:
                        pass
                if ps_state == checkpoint_state:
                    break

        # Resume execution from the next stage
        for stage in remaining_stages:
            if stage not in stage_handlers:
                continue

            result = await self.execute_stage(
                stage=stage,
                handler=stage_handlers[stage],
                context=context,
                passport=passport,
                session_id=checkpoint.session_id,
            )

            if result is None:
                return None

            context["results"][stage.value] = result

        return context
