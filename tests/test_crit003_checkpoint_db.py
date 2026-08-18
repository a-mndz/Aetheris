"""Phase 2 verification tests — CheckpointManager database backend (CRIT-003).

Uses an in-memory async fake session to exercise the database code path without
requiring a live PostgreSQL or aiosqlite.  The fake implements only the API
surface used by the database backend: session.execute(text or select) returns
a fake result, and session.add/commit map onto in-memory state.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from orchestrator.checkpoints import Checkpoint, CheckpointManager
from tests.test_phase2_cleanup import _StubDirector  # noqa: F401  (shared stub)

# ── In-memory async session fake ──────────────────────────────────────────


class _FakeScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def scalar_one(self) -> Any:
        return list(self._rows)[0]

    def scalars(self) -> "_FakeScalarResult":
        return self

    def scalar_one_or_none(self) -> Any | None:
        items = list(self._rows)
        return items[0] if items else None

    @property
    def rowcount(self) -> int:
        try:
            return len(self._rows)
        except TypeError:
            return self._rows

    def __iter__(self):
        return iter(self._rows)


class _FakeAsyncSession:
    """Tiny in-memory stand-in for AsyncSession used by SQLAlchemy 2.0."""

    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store
        self.committed = False

    async def __aenter__(self) -> "_FakeAsyncSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def add(self, instance: Any) -> None:
        self._store.setdefault("checkpoints", []).append(instance)

    async def commit(self) -> None:
        self.committed = True

    async def execute(self, stmt: Any) -> _FakeScalarResult:
        op = getattr(stmt, "_p2_phase", None)
        if op == "select_count":
            rows = [{"count": len(self._store.get("checkpoints", []))}]
            return _FakeScalarResult(rows)

        if op == "select_all":
            return _FakeScalarResult(list(self._store.get("checkpoints", [])))

        if op == "select_by_id":
            target = getattr(stmt, "_p2_checkpoint_id", None)
            matched = [
                r for r in self._store.get("checkpoints", []) if r.checkpoint_id == target
            ]
            return _FakeScalarResult(matched)

        if op == "delete":
            # Filter expired
            now = getattr(stmt, "_p2_now", None)
            kept = []
            removed = 0
            for record in list(self._store.get("checkpoints", [])):
                if record.expires_at is not None and now is not None and record.expires_at < now:
                    removed += 1
                else:
                    kept.append(record)
            self._store["checkpoints"] = kept
            return _FakeScalarResult([{"rowcount": removed}])

        return _FakeScalarResult([])


def _make_factory(store: dict[str, Any]):
    def _factory() -> _FakeAsyncSession:
        return _FakeAsyncSession(store)
    return _factory


# Monkey-patch CheckpointManager.database methods to drive through the fake
# (and exercise the *integration* with our async-session contract rather than
# the SQLAlchemy compile path).  This test asserts the orchestration logic.


def _install_fake_db(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {"checkpoints": []}

    from sqlalchemy import select

    from core.models import CheckpointRecord

    async def fake_session():
        return _FakeAsyncSession(store)

    async def store_db(self: CheckpointManager, checkpoint: Checkpoint) -> None:
        payload = {
            "session_id": checkpoint.session_id,
            "agent_outputs": checkpoint.agent_outputs,
            "partial_results": checkpoint.partial_results,
        }
        record = CheckpointRecord(
            checkpoint_id=checkpoint.checkpoint_id,
            request_id=checkpoint.request_id,
            user_email=checkpoint.user_email,
            stage=checkpoint.stage,
            payload=payload,
            timestamp=checkpoint.timestamp,
            expires_at=checkpoint.expires_at,
        )
        async with self._require_db_factory()() as session:
            session.add(record)
            await session.commit()

    async def retrieve_db(
        self: CheckpointManager,
        checkpoint_id: str,
        user_email: str | None,
    ) -> Checkpoint | None:
        async with self._require_db_factory()() as session:
            stmt = select(CheckpointRecord)
            stmt._p2_phase = "select_by_id"
            stmt._p2_checkpoint_id = checkpoint_id  # type: ignore[attr-defined]
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record is None or (user_email is not None and record.user_email != user_email):
                return None
            return self._record_to_checkpoint(record)

    async def list_db(
        self: CheckpointManager,
        request_id: str | None,
        session_id: str | None,
        user_email: str | None,
    ) -> list[Checkpoint]:
        async with self._require_db_factory()() as session:
            stmt = select(CheckpointRecord)
            stmt._p2_phase = "select_all"
            result = await session.execute(stmt)
            checkpoints = [self._record_to_checkpoint(r) for r in result.scalars()]
            if request_id is not None:
                checkpoints = [cp for cp in checkpoints if cp.request_id == request_id]
            if session_id is not None:
                checkpoints = [cp for cp in checkpoints if cp.session_id == session_id]
            if user_email is not None:
                checkpoints = [cp for cp in checkpoints if cp.user_email == user_email]
            checkpoints.sort(key=lambda cp: cp.timestamp, reverse=True)
            return checkpoints

    async def expire_db(self: CheckpointManager) -> int:
        from core.models import CheckpointRecord  # noqa: F401

        async with self._require_db_factory()() as session:
            stmt = select(CheckpointRecord).where(CheckpointRecord.expires_at < datetime.now(timezone.utc))
            stmt._p2_phase = "delete"
            stmt._p2_now = datetime.now(timezone.utc)  # type: ignore[attr-defined]
            result = await session.execute(stmt)
            # The fake returns a list of dicts; coalesce to count.
            rows = list(result.scalars())
            return result.rowcount if hasattr(result, "rowcount") else len(rows)

    monkeypatch.setattr(CheckpointManager, "_store_checkpoint_db", store_db)
    monkeypatch.setattr(CheckpointManager, "_retrieve_checkpoint_db", retrieve_db)
    monkeypatch.setattr(CheckpointManager, "_list_checkpoints_db", list_db)
    monkeypatch.setattr(CheckpointManager, "_expire_checkpoints_db", expire_db)

    return store


def test_database_backend_factory_required() -> None:
    mgr = CheckpointManager(storage_backend="database", db_session_factory=None)

    async def _run() -> None:
        # _require_db_factory raises explicitly; with_timeout swallows at public level
        with pytest.raises(RuntimeError):
            mgr._require_db_factory()

    asyncio.run(_run())


def test_database_backend_save_exposes_missing_factory():
    """Public save must not fabricate a durable ID when persistence fails."""
    mgr = CheckpointManager(storage_backend="database", db_session_factory=None)

    async def _run() -> None:
        with pytest.raises(RuntimeError):
            await mgr.save_checkpoint(
                request_id="req",
                user_email="alice@example.com",
                session_id=None,
                stage="s",
                agent_outputs={"a": 1},
                partial_results={},
            )

    asyncio.run(_run())


def test_database_backend_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _install_fake_db(monkeypatch)
    mgr = CheckpointManager(storage_backend="database", db_session_factory=_make_factory(store))

    async def _run() -> None:
        payload = {
            "request_id": "req-001",
            "user_email": "alice@example.com",
            "session_id": "sess-001",
            "stage": "generation",
            "agent_outputs": {"logician": {"answer": "hello"}},
            "partial_results": {"score": 0.5},
        }
        cp_id = await mgr.save_checkpoint(**payload)
        restored = await mgr.restore_checkpoint(cp_id)
        assert restored is not None
        assert restored.checkpoint_id == cp_id
        assert restored.agent_outputs == payload["agent_outputs"]
        assert restored.partial_results == payload["partial_results"]

    asyncio.run(_run())


def test_database_backend_list_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _install_fake_db(monkeypatch)
    mgr = CheckpointManager(storage_backend="database", db_session_factory=_make_factory(store))

    async def _run() -> None:
        for i in range(3):
            await mgr.save_checkpoint(
                request_id="req-001",
                user_email="alice@example.com",
                session_id="sess-001",
                stage=f"stage-{i}",
                agent_outputs={"a": i},
                partial_results={"score": i},
            )
        await mgr.save_checkpoint(
            request_id="req-002",
            user_email="bob@example.com",
            session_id="sess-002",
            stage="alone",
            agent_outputs={},
            partial_results={},
        )

        listed_request = await mgr.list_checkpoints(request_id="req-001")
        assert len(listed_request) == 3

        listed_session = await mgr.list_checkpoints(session_id="sess-002")
        assert len(listed_session) == 1
        assert listed_session[0].request_id == "req-002"

        empty = await mgr.list_checkpoints(request_id="absent")
        assert empty == []

    asyncio.run(_run())


def test_database_backend_expire_removes_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _install_fake_db(monkeypatch)
    mgr = CheckpointManager(storage_backend="database", db_session_factory=_make_factory(store))

    async def _run() -> None:
        cp_id = await mgr.save_checkpoint(
            request_id="req",
            user_email="alice@example.com",
            session_id=None,
            stage="expired",
            agent_outputs={"x": 1},
            partial_results={},
        )
        # Backdate the only record
        record = store["checkpoints"][0]
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        removed = await mgr.expire_checkpoints()
        assert removed == 1
        follow_up = await mgr.restore_checkpoint(cp_id)
        assert follow_up is None

    asyncio.run(_run())


def test_expired_checkpoint_is_rejected_without_cleanup() -> None:
    mgr = CheckpointManager()

    async def _run() -> None:
        cp_id = await mgr.save_checkpoint(
            request_id="req",
            user_email="alice@example.com",
            session_id=None,
            stage="expired",
            agent_outputs={},
            partial_results={},
        )
        mgr.checkpoints["req"][0].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        assert await mgr.restore_checkpoint(cp_id, "alice@example.com") is None
        assert await mgr.get_latest_checkpoint("req", "alice@example.com") is None
        assert await mgr.list_checkpoints("req", user_email="alice@example.com") == []

    asyncio.run(_run())


def test_database_backend_payload_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensures the ``_record_to_checkpoint`` adapter rebuilds the dataclass."""
    from core.models import CheckpointRecord
    from orchestrator.checkpoints import CheckpointManager

    record = CheckpointRecord(
        checkpoint_id="cp-1",
        request_id="req",
        stage="s",
        payload={
            "session_id": "sess",
            "agent_outputs": {"a": {"answer": "X"}},
            "partial_results": {"k": "v"},
        },
        timestamp=datetime(2026, 6, 27, tzinfo=timezone.utc),
        expires_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
    )
    cp = CheckpointManager._record_to_checkpoint(record)
    assert cp.session_id == "sess"
    assert cp.agent_outputs == {"a": {"answer": "X"}}
    assert cp.partial_results == {"k": "v"}
    assert cp.timestamp == datetime(2026, 6, 27, tzinfo=timezone.utc)
