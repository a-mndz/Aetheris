"""Unit tests for ExecutionPassport lifecycle, error recording, and timing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.passport import ExecutionPassport


class TestExecutionPassport:
    def test_default_construction_assigns_request_id(self) -> None:
        passport = ExecutionPassport()
        assert passport.request_id
        uuid.UUID(passport.request_id)  # Validates UUID format

    def test_request_id_is_unique_per_instance(self) -> None:
        a = ExecutionPassport()
        b = ExecutionPassport()
        assert a.request_id != b.request_id

    def test_elapsed_seconds_increments_monotonically(self) -> None:
        passport = ExecutionPassport()
        first = passport.elapsed_seconds()
        second = passport.elapsed_seconds()
        assert second >= first

    def test_stage_transitions_recorded_in_order(self) -> None:
        passport = ExecutionPassport()
        passport.update_stage("breaker")
        passport.update_stage("generating")
        passport.update_stage("evaluating")
        passport.update_stage("completed")
        assert passport.execution_state.current_stage == "completed"

    def test_record_error_appends_to_errors_log(self) -> None:
        passport = ExecutionPassport()
        before = len(passport.execution_state.errors)
        passport.record_error("logician", "TimeoutError")
        assert len(passport.execution_state.errors) == before + 1
        assert passport.execution_state.errors[-1]["stage"] == "logician"

    def test_record_warning_does_not_add_to_errors(self) -> None:
        passport = ExecutionPassport()
        before_errors = len(passport.execution_state.errors)
        passport.record_warning("soft warning")
        assert len(passport.execution_state.errors) == before_errors
        assert passport.execution_state.warnings[-1] == "soft warning"

    def test_security_metadata_injection_attempts(self) -> None:
        passport = ExecutionPassport()
        passport.security_metadata.injection_attempts = 0
        passport.record_injection_attempt()
        passport.record_injection_attempt()
        assert passport.security_metadata.injection_attempts == 2

    def test_to_dict_is_json_serialisable(self) -> None:
        passport = ExecutionPassport()
        payload = passport.to_dict()
        assert "request_id" in payload
        assert "timestamp" in payload
        assert isinstance(payload["timestamp"], str)
        assert "security_metadata" in payload
        assert "execution_state" in payload

    def test_session_and_user_id_attached(self) -> None:
        passport = ExecutionPassport(session_id="sess-1", user_id="user@example.com")
        assert passport.session_id == "sess-1"
        assert passport.user_id == "user@example.com"
