# Database Subsystem Report

| Field | Value |
|-------|-------|
| **Subsystem ID** | S5 — Database |
| **Core Files** | `core/database.py`, `core/models.py`, `alembic.ini`, `migrations/**` |
| **Health Score (Pre-Phase 1)** | 30/100 |
| **Health Score (Post-Phase 1)** | 65/100 |
| **Δ Health** | +35 |
| **Status** | 🟡 Fair (Foundation laid; backend switch in Phase 2) |
| **Report Date** | 2026-06-27 |

---

## 1. Repairs

### 1.1 CRIT-006 — Alembic Migrations

| Field | Value |
|-------|-------|
| **Status** | ✅ Verified |
| **Repair ID** | REP-000901 |
| **Files** | `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/001_initial_schema.py` |

There was no migration system — schema was bootstrapped via `Base.metadata.create_all` on every startup.

**Repair**:

- `alembic.ini` configured with `script_location = migrations`, `timezone = UTC`, logger/handler/formatter blocks.
- `migrations/env.py` consumes `core.database.Base.metadata` and pulls DATABASE_URL from `core.config.get_settings()` at runtime.
- `migrations/script.py.mako` template ready.
- `001_initial_schema.py` builds every application table with PKs, FKs, indexes, and JSON columns for checkpoints/telemetry payloads.
- `alembic upgrade head` brings a fresh database to the current schema; `alembic downgrade -1` reverts to nothing.

**Validation**: `test_alembic_binary_present`, `test_alembic_ini_exists`, `test_migrations_env_exists`, `test_initial_revision_present`, `test_env_loads_target_metadata`.

### 1.2 HIGH-016 — Database SSL

| Field | Value |
|-------|-------|
| **Status** | ✅ Verified |
| **Repair ID** | REP-000901 |
| **Files** | `core/database.py`, `core/config.py` |

`engine = create_async_engine(..., connect_args={"ssl": False})` hardcoded cleartext traffic regardless of environment.

**Repair**:

- `core/config.py` adds `DATABASE_SSL: bool = Field(default=False, validation_alias="DATABASE_SSL")`.
- `core/database.py` builds `connect_args={"ssl": settings.DATABASE_SSL}`.

**Validation**: `test_default_ssl_is_false`, `test_ssl_can_be_enabled`.

### 1.3 MED-025 — Pool Recycling

`engine = create_async_engine(..., pool_recycle=3600)` added; long-idle connections are recycled before NAT/firewall idle timeouts silently drop them.

### 1.4 HIGH-017 — Database Models

| Field | Value |
|-------|-------|
| **Status** | 🟡 Models declared; backend switch deferred to Phase 2 |
| **Repair ID** | REP-000901 |
| **Files** | `core/models.py` |

Only the `User` model existed. Phase 1 adds the models; Phase 2 wires `ConversationDirector`, `CheckpointManager`, and telemetry persistence to them.

**Repair**:

- `class ConversationSessionRecord` — `__tablename__ = "conversation_sessions"` with `session_id`, `owner_email` (HIGH-015 enforcement), `state`, `total_tokens`, `turn_count`, `created_at`, `expires_at`. Companion `ConversationMessageRecord` for messages with FK + cascade delete.
- `class CheckpointRecord` — `__tablename__ = "checkpoints"` with `checkpoint_id`, `request_id`, `user_email`, `stage`, JSON `payload`, `timestamp`, `expires_at`.
- `class TelemetryEvent` — `__tablename__ = "telemetry_events"` with `request_id`, `user_email`, `stage`, `event_type`, `duration_ms`, `cost_usd`, JSON `payload`.
- `User` enriched: `role` (default `"user"`, MED-023 prep), `updated_at` with `onupdate`.

**Validation**: `test_session_message_models_present`, `test_checkpoint_model_present`, `test_telemetry_model_present`, `test_models_register_with_same_metadata`.

---

## 2. Files Touched

| File | Status |
|------|--------|
| `core/database.py` | Modified |
| `core/models.py` | Modified (rewritten with new classes) |
| `core/config.py` | Modified (DATABASE_SSL field) |
| `alembic.ini` | Created |
| `migrations/env.py` | Created |
| `migrations/script.py.mako` | Created |
| `migrations/versions/001_initial_schema.py` | Created |
| `tests/test_database_repair.py` | Created |

---

## 3. Validation

| Gate | Status |
|------|--------|
| Compilation | ✅ Pass |
| Ruff | ✅ No new issues |
| Unit tests | 12/12 |
| Migration consistency | ✅ Initial migration matches `Base.metadata` |

---

## 4. Remaining Risks

| Risk | Severity | Notes |
|------|----------|-------|
| `ConversationDirector._sessions` still uses in-memory dict | 🟡 Medium | Phase 2 must replace with DB-backed implementation (MED-007) |
| `CheckpointManager(storage_backend="memory")` initial state | 🟡 Medium | Phase 2 must switch to DB-backed (CRIT-003) |
| `pool_recycle=3600` was Phase 3 work delivered early | 🟢 Low | Backwards-compatible; documents the early delivery |
| Schema portability (JSON vs JSONB) | 🟢 Low | Alembic env targets PostgreSQL JSONB; SQLite handles via Python type adapter |

---

## 5. Recommendations

- Phase 2 should make `ConversationDirector` optionally SQL-backed with a config flag (`aetheris_SESSION_BACKEND=database|memory`, default database).
- Phase 2 should swap `CheckpointManager` to `storage_backend="database"` and persist JSON checkpoints.
- Phase 2 should add Alembic autogenerate pre-commit hook.
- Phase 3 should add Prometheus metrics around pool checkout time (LOW-026).

---

## 6. Audit Index Status

| Issue ID | Old Status | New Status |
|----------|------------|------------|
| CRIT-006 | 🔴 Open | ✅ Verified |
| HIGH-016 | 🔴 Open | ✅ Verified |
| HIGH-017 | 🟠 Open | 🟡 Models declared; backend switch in Phase 2 |
| MED-025 | (Phase 3) | ✅ Verified (early delivery) |
| LOW-026 | 🟢 Open | Still open — connection pool monitoring (Phase 4) |
| LOW-027 | 🟢 Open | Still open — `is_active` for soft delete (Phase 4) |
| LOW-028 | 🟢 Open | Still open — SSE stream DB connection release (Phase 4) |
