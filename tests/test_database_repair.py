"""Phase 1 — Database subsystem targeted regression tests.

Covers CRIT-006 (Alembic available), HIGH-016 (DB SSL configurable),
HIGH-017 (additional SQLAlchemy models).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


class TestHIGH016DatabaseSSLConfigurable:
    def test_default_ssl_is_false(self) -> None:
        os.environ.pop("DATABASE_SSL", None)
        from core.config import aetherisConfig
        s = aetherisConfig(_env_file=None, JWT_SECRET_KEY=os.environ["AETHERIS_JWT_SECRET_KEY"])
        assert s.DATABASE_SSL is False

    def test_ssl_can_be_enabled(self) -> None:
        from core.config import aetherisConfig
        s = aetherisConfig(
            _env_file=None,
            DATABASE_SSL=True,
            JWT_SECRET_KEY=os.environ["AETHERIS_JWT_SECRET_KEY"],
        )
        assert s.DATABASE_SSL is True


class TestHIGH017ModelsDeclared:
    def test_user_model_present(self) -> None:
        from core.models import User
        assert "users" in User.metadata.tables

    def test_session_message_models_present(self) -> None:
        from core.models import ConversationMessageRecord, ConversationSessionRecord
        assert "conversation_sessions" in ConversationSessionRecord.metadata.tables
        assert "conversation_messages" in ConversationMessageRecord.metadata.tables

    def test_checkpoint_model_present(self) -> None:
        from core.models import CheckpointRecord
        assert "checkpoints" in CheckpointRecord.metadata.tables

    def test_telemetry_model_present(self) -> None:
        from core.models import TelemetryEvent
        assert "telemetry_events" in TelemetryEvent.metadata.tables

    def test_models_register_with_same_metadata(self) -> None:
        from core.models import (
            CheckpointRecord,
            ConversationSessionRecord,
            TelemetryEvent,
            User,
        )
        tables = set()
        for cls in (User, ConversationSessionRecord, CheckpointRecord, TelemetryEvent):
            tables.update(cls.metadata.tables.keys())
        # All five app tables live on the shared Base.metadata
        assert {"users", "conversation_sessions", "conversation_messages", "checkpoints", "telemetry_events"}.issubset(tables)


class TestCRIT006AlembicAvailable:
    def test_alembic_binary_present(self) -> None:
        import shutil
        assert shutil.which("alembic") is not None or shutil.which("alembic.exe") is not None

    def test_alembic_ini_exists(self) -> None:
        assert Path("alembic.ini").exists()

    def test_migrations_env_exists(self) -> None:
        assert Path("migrations/env.py").exists()

    def test_initial_revision_present(self) -> None:
        revisions = list(Path("migrations/versions").glob("*.py"))
        assert any("001_initial_schema" in str(p) for p in revisions)

    def test_env_loads_target_metadata(self) -> None:
        # We cannot actually run alembic upgrade here (no PostgreSQL), but
        # the env module must reference the metadata — verified by reading
        # the source rather than importing (importing would attempt to read
        # alembic.ini from the working directory).
        source = Path("migrations/env.py").read_text(encoding="utf-8")
        assert "target_metadata" in source
        assert "Base.metadata" in source
