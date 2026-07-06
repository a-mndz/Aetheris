"""Unit tests for StateMachine transitions (Phase 1 coverage of existing API)."""

from __future__ import annotations

import pytest

from orchestrator.state_machine import (
    InvalidTransitionError,
    PipelineState,
    StateMachine,
)


class TestStateMachineHappyPath:
    def test_idle_is_initial(self) -> None:
        sm = StateMachine(request_id="req-1")
        assert sm.current_state == PipelineState.IDLE

    def test_idle_to_normalizing_to_breach_checking_to_generating(self) -> None:
        sm = StateMachine(request_id="req-2")
        sm.transition(PipelineState.NORMALIZING)
        assert sm.current_state == PipelineState.NORMALIZING
        sm.transition(PipelineState.BREACH_CHECKING)
        assert sm.current_state == PipelineState.BREACH_CHECKING
        sm.transition(PipelineState.GENERATING)
        assert sm.current_state == PipelineState.GENERATING

    def test_terminal_completed(self) -> None:
        sm = StateMachine(request_id="req-3")
        sm.transition(PipelineState.NORMALIZING)
        sm.transition(PipelineState.BREACH_CHECKING)
        sm.transition(PipelineState.GENERATING)
        sm.transition(PipelineState.EVALUATING)
        sm.transition(PipelineState.SYNTHESIZING)
        sm.transition(PipelineState.FORMATTING)
        sm.transition(PipelineState.COMPLETED)
        assert sm.current_state == PipelineState.COMPLETED


class TestStateMachineInvalidTransitions:
    def test_skip_states_rejected_from_idle(self) -> None:
        sm = StateMachine(request_id="req-skip")
        with pytest.raises(InvalidTransitionError):
            sm.transition(PipelineState.EVALUATING)
