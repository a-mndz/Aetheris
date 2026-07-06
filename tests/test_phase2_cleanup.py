"""Phase 2 repair verification tests — backend cleanup and consolidation.

Covers REP-001001 (HIGH-003 dead-code purge + MED-004 helper consolidation),
REP-001002 (HIGH-006/HIGH-007 archive), and MED-015 (user-query recording).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


# ── Stubs ─────────────────────────────────────────────────────────────────


@dataclass
class _StubSession:
    history: list = field(default_factory=list)
    total_tokens: int = 0
    state: str = "ACTIVE"


class _StubDirector:
    """Tiny ConversationDirector stub: tracks state + history."""

    def __init__(self, ephemeral: bool = True) -> None:
        self.ephemeral = ephemeral
        self._sessions: dict[str, _StubSession] = {}
        self.error_on_transition = False

    def create_session(self, sid: str) -> None:
        self._sessions[sid] = _StubSession()

    def get_session(self, sid: str):
        return self._sessions.get(sid)

    def should_truncate(self, sid: str) -> bool:
        return False

    def truncate_history(self, sid: str) -> str | None:
        return None

    def get_history(self, sid: str) -> list[dict[str, str]]:
        sess = self._sessions.get(sid)
        if sess is None:
            return []
        return [
            {"role": t["role"], "content": t["content"]} for t in sess.history
        ]

    def get_metadata(self, sid: str) -> dict[str, Any] | None:
        sess = self._sessions.get(sid)
        return {"session_id": sid, "state": sess.state} if sess else None

    def add_turn(self, sid: str, role: str, content: str, token_count: int = 0) -> None:
        sess = self._sessions[sid]
        sess.history.append({"role": role, "content": content, "tokens": token_count})
        sess.total_tokens += token_count

    def transition_state(self, sid: str, state: Any) -> None:
        if self.error_on_transition:
            raise RuntimeError("intentional fault")
        self._sessions[sid].state = state.value


# ── MED-004 / MED-016: _mark_conversation_failed consolidation ─────────────


def test_mark_conversation_failed_transitions_when_director_provided():
    from orchestrator.pipelines import _mark_conversation_failed

    director = _StubDirector()
    director.create_session("s1")
    result = _mark_conversation_failed(director, "s1")
    assert result == {"session_id": "s1", "state": "FAILED"} or result == {
        "session_id": "s1",
        "state": "failed",
    }


def test_mark_conversation_failed_returns_none_without_director():
    from orchestrator.pipelines import _mark_conversation_failed

    assert _mark_conversation_failed(None, "s1") is None


def test_mark_conversation_failed_returns_none_without_session_id():
    from orchestrator.pipelines import _mark_conversation_failed

    director = _StubDirector()
    assert _mark_conversation_failed(director, None) is None
    assert _mark_conversation_failed(director, "") is None


def test_mark_conversation_failed_swallows_transition_errors():
    from orchestrator.pipelines import _mark_conversation_failed

    director = _StubDirector()
    director.create_session("s1")
    director.error_on_transition = True
    assert _mark_conversation_failed(director, "s1") is None


def test_mark_conversation_failed_handles_missing_session():
    from orchestrator.pipelines import _mark_conversation_failed

    director = _StubDirector()
    assert _mark_conversation_failed(director, "absent") is None


# ── MED-015: record_user_query ────────────────────────────────────────────


def test_record_user_query_appends_role_user_turn():
    from agents.prompt_utils import record_user_query

    director = _StubDirector()
    director.create_session("s1")
    record_user_query(director, "s1", "Why is the sky blue?", None)
    history = director.get_history("s1")
    assert history == [{"role": "user", "content": "Why is the sky blue?"}]


def test_record_user_query_estimates_token_count():
    from agents.prompt_utils import record_user_query

    director = _StubDirector()
    director.create_session("s1")
    record_user_query(director, "s1", "a" * 80, None)
    sess = director.get_session("s1")
    assert sess.total_tokens == 20


def test_record_user_query_no_op_when_inputs_missing():
    from agents.prompt_utils import record_user_query

    director = _StubDirector()
    director.create_session("s1")
    record_user_query(None, "s1", "anything", None)
    record_user_query(director, None, "anything", None)
    record_user_query(director, "s1", None, None)
    record_user_query(director, "s1", "", None)
    assert director.get_session("s1").history == []


def test_record_user_query_swallows_missing_session():
    from agents.prompt_utils import record_user_query

    director = _StubDirector()
    record_user_query(director, "missing", "hello", None)


# ── HIGH-006 archive: active personas ────────────────────────────────────


def test_verifier_skeptic_removed_from_registry():
    from agents.personas import PERSONA_REGISTRY

    assert "verifier" not in PERSONA_REGISTRY
    assert "skeptic" not in PERSONA_REGISTRY
    assert "breaker" in PERSONA_REGISTRY
    assert "logician" in PERSONA_REGISTRY
    assert "creative" in PERSONA_REGISTRY


# ── HIGH-007 archive: SignalState removed ─────────────────────────────────


def test_signal_state_no_longer_exported():
    import importlib

    from core import schemas as schemas_module

    importlib.reload(schemas_module)
    assert not hasattr(schemas_module, "SignalState")


def test_pipeline_imports_cleanly_after_archive():
    import importlib

    mod = importlib.import_module("orchestrator.pipelines")
    importlib.reload(mod)
    for name in ("_mark_conversation_failed", "run_micro_mode", "stream_micro_mode"):
        assert hasattr(mod, name), name
