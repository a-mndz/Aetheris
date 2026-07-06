# AETHERIS Database Audit

**Audit Date:** 2026-06-27
**Auditor:** Principal Database Engineer
**Scope:** Complete static analysis of the PostgreSQL database schema, SQLAlchemy ORM models, connection pooling, migrations, caching, query patterns, and data integrity.

---

## Table of Contents

1. [Database Architecture Overview](#1-database-architecture-overview)
2. [Schema & Models](#2-schema--models)
3. [Indexes](#3-indexes)
4. [Relationships & Foreign Keys](#4-relationships--foreign-keys)
5. [Normalization](#5-normalization)
6. [Constraints & Data Integrity](#6-constraints--data-integrity)
7. [Migrations](#7-migrations)
8. [Connection Pooling](#8-connection-pooling)
9. [Caching](#9-caching)
10. [Query Analysis](#10-query-analysis)
11. [Security & Configuration](#11-security--configuration)
12. [Issue Register](#12-issue-register)

---

## 1. Database Architecture Overview

### Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Database | PostgreSQL | Unknown (via asyncpg) |
| ORM | SQLAlchemy 2.0 (async) | ≥ 2.0.0 |
| Driver | asyncpg | ≥ 0.29.0 |
| Connection Pool | SQLAlchemy pool (QueuePool) | Built-in |

### Configuration

```python
# core/database.py:16-26
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"ssl": False},
)
```

**Database URL (from .env):**
```
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/postgres
```

### Current Database Usage

| Feature | Status | Details |
|---------|--------|---------|
| User authentication | ✅ | Register, login, JWT validation |
| Session persistence | 🔴 | In-memory only (ConversationDirector) |
| Checkpoint storage | 🔴 | Memory-only backend |
| Conversation history | 🔴 | Frontend localStorage only |
| Provider health data | 🔴 | In-memory (ProviderPool) |
| Telemetry data | 🔴 | In-memory (TelemetryObserver) |
| Claim/knowledge data | 🔴 | In-memory (ReasoningGraph) |
| Pipeline execution state | 🔴 | In-memory (EpistemicMemory) |

The database is used **exclusively for user authentication**. All other persistent data is stored in-memory and lost on restart.

---

## 2. Schema & Models

### Complete Schema

**Only model:** `User` (table: `users`)

```python
# core/models.py:14-30
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
```

### Generated DDL

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_users_email ON users (email);
```

### Missing Models

The following data concepts have no database model:

| Concept | Current Storage | Impact |
|---------|----------------|--------|
| Conversation sessions | `ConversationDirector._sessions` (dict) | Lost on restart |
| Conversation history | Frontend localStorage | Lost on browser clear |
| Pipeline checkpoints | `CheckpointManager.checkpoints` (dict) | Lost on restart |
| Provider health | `ProviderPool._providers` (dict) | Lost on restart |
| Telemetry data | `TelemetryObserver` instance | Lost on restart |
| Claims/knowledge | `ReasoningGraph._nodes/_edges` (dict) | Lost on restart |
| Failure history | `EpistemicMemory.failed_loops` (deque) | Lost on restart |
| Execution passports | Not persisted at all | Lost after response |
| API key usage logs | Flat file (`logs/model_io.log`) | Unstructured, no rotation |

---

## 3. Indexes

### Current Indexes

| Index | Column | Type | Purpose |
|-------|--------|------|---------|
| `ix_users_email` | `email` | B-tree (unique) | Login lookup by email |

### Index Analysis

**Coverage: Insufficient** — Only one index exists for the entire schema. All queries are simple `SELECT ... WHERE email = ?` lookups, which the single index covers. However, no indexes exist for:

- **Timestamps**: No index on `created_at` for session expiry queries or data cleanup
- **Foreign keys**: No foreign keys exist, so no FK indexes needed
- **Full-text search**: No `tsvector` index for searching across conversation content (not yet in DB)

### Query Patterns

All three database queries follow the same pattern:
```python
stmt = select(User).where(User.email == req.email)
result = await db.execute(stmt)
user = result.scalars().first()
```

The existing index on `email` is optimal for this query pattern.

---

## 4. Relationships & Foreign Keys

### Status: 🔴 NONE

There are **no relationships or foreign keys** in the schema. The `User` model has no relations to any other tables because no other tables exist.

When additional models are added (sessions, checkpoints, etc.), foreign key relationships will be needed:

| Entity | Foreign Key | Type |
|--------|------------|------|
| ConversationSession | user_id → users.id | Many-to-one |
| Checkpoint | request_id → ... | TBD |
| Telemetry | user_id → users.id | Many-to-one |
| ProviderLog | user_id → users.id | Many-to-one |

---

## 5. Normalization

### Assessment: N/A (single table)

With only one table, normalization cannot be assessed. The schema is trivially in BCNF (no functional dependencies beyond the primary key).

### Future Normalization Risk

When the schema expands, careful normalization will be needed:

1. **Users/Sessions**: A user has many sessions. Sessions should reference `users.id` via FK.
2. **Sessions/Messages**: A session has many messages. Messages should reference session ID via FK.
3. **Sessions/Checkpoints**: A session can have many checkpoints (or a request can have many checkpoints). Needs normalization decision.
4. **Provider metadata**: Provider names, models, pricing are currently hardcoded in Python dicts. Could be normalized into `providers` and `provider_models` tables.

---

## 6. Constraints & Data Integrity

### Existing Constraints

| Constraint | Column | Status |
|------------|--------|--------|
| PRIMARY KEY | `users.id` | ✅ |
| UNIQUE | `users.email` | ✅ |
| NOT NULL | `users.email` | ✅ |
| NOT NULL | `users.password_hash` | ✅ |
| NOT NULL | `users.created_at` | ✅ |
| CHECK | None | ❌ |

### Missing Constraints

| Constraint | Purpose | Impact |
|------------|---------|--------|
| Email format CHECK | Validates email format at DB level | Invalid emails pass ORM validation but could be stored |
| Password hash length | Could enforce minimum hash length | bcrypt hashes are always 60 chars, so VARCHAR(255) is generous |
| No delete cascade | When user is deleted, all user data is orphaned | Not yet an issue (only one table) |

### Data Integrity Risks

1. **No email validation at DB level**: The `String(255)` type accepts any string, including non-email values. The application layer does not validate email format before storing.

2. **No created_at default enforcement**: The default is set at the Python level (`default=lambda: datetime.now(timezone.utc)`). If the column is omitted from an INSERT, SQLAlchemy applies the Python default. But raw SQL inserts or direct DB operations could insert NULL.

3. **No check constraint on password_hash**: While bcrypt always produces 60-char hashes, there is no DB-level constraint preventing shorter or malformed hashes.

---

## 7. Migrations

### Status: 🔴 NONE

**No migration system exists.** There is no `alembic.ini`, no `migrations/` directory, and no migration scripts anywhere in the project.

### Current Schema Management

```python
# server.py:91-110
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

Tables are created at startup via `Base.metadata.create_all`. This approach:
- Creates tables that don't exist (safe for initial deployment)
- **Does NOT alter existing tables** (columns added to models are not applied)
- **Does NOT track schema versions** (no upgrade/downgrade path)
- **Cannot migrate data** (no transformation scripts)
- **Cannot roll back** failed schema changes

### Migration Risk

Any schema change (adding a column, creating a new table, adding an index) requires either:
1. Manual SQL execution in production
2. Dropping and recreating the database (losing all data)
3. Writing ad-hoc migration scripts

This is a critical issue for any production deployment.

---

## 8. Connection Pooling

### Current Configuration

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"ssl": False},
)
```

| Parameter | Value | Assessment |
|-----------|-------|------------|
| `pool_size` | 20 | ✅ Reasonable for moderate concurrency |
| `max_overflow` | 10 | ✅ Allows burst traffic up to 30 connections |
| `pool_pre_ping` | True | ✅ Checks connection health before use |
| `pool_recycle` | Not set (default: -1) | ⚠️ No connection recycling |
| `pool_timeout` | Not set (default: 30s) | ⚠️ Can block for 30s on exhausted pool |
| `poolclass` | Not set (default: QueuePool) | ✅ Standard choice |

### Connection Pool Analysis

**Maximum concurrent connections:** 30 (20 pool + 10 overflow)

**Current usage:** The database is only used for auth queries (register, login, `get_current_user`). Each API request uses the `get_db` dependency:
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_maker()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

**Issue:** `get_db` is only injected into `/auth/register` and `/auth/login` endpoints. All other API endpoints use `Depends(get_current_user)` which calls `get_db` internally. This means:
- Every API call consumes one database connection (for `get_current_user`)
- SSE streaming connections hold a DB connection for the duration of the stream (potentially minutes)
- The pool of 30 could be exhausted by concurrent SSE streams alone

### Missing Configuration

1. **No `pool_recycle`**: Without connection recycling, long-idle connections may be closed by the database or network middleboxes, causing "connection closed" errors on the next query.

2. **No `pool_timeout` override**: The default 30-second `pool_timeout` means a request could wait 30 seconds for a connection if the pool is exhausted, blocking the event loop thread.

3. **No connection monitoring**: There are no metrics or logging for pool utilization, wait times, or connection errors.

---

## 9. Caching

### Status: 🔴 NONE

There is **no caching layer** in the application:

| Cache Type | Status | Details |
|------------|--------|---------|
| Redis/Memcached | ❌ | Not installed, not imported |
| In-memory cache | ❌ | No `functools.lru_cache` on DB queries |
| Query cache | ❌ | SQLAlchemy query cache not configured |
| HTTP cache | ❌ | Only `Cache-Control: no-cache` on SSE |
| Frontend cache | ⚠️ | localStorage for conversations only |

### Impact

1. **`get_current_user` on every request**: Each API call queries the database for the user record. A user making many requests causes repeated identical queries:
   ```python
   select(User).where(User.email == email)  # Same query, same result, every time
   ```

2. **SSE streaming holds DB connection**: The streaming endpoint calls `get_db` which creates a DB session for the duration of the stream. A 2-minute pipeline execution holds a DB connection the entire time.

3. **No API response caching**: Pipeline results, telemetry data, and provider health are never cached. Repeated requests for the same query re-execute the full pipeline.

### Caching Opportunities

| Query | Frequency | Cache Strategy | Benefit |
|-------|-----------|---------------|---------|
| `get_current_user` | Every API request | Short TTL (5min) user cache by email | Eliminates 90%+ of DB queries |
| Provider health | Health poll every 30s | Short TTL (10s) in-memory | Reduces backend computation |
| Configuration data | Rarely changes | Load on startup, never expire | Zero queries |

---

## 10. Query Analysis

### All Database Queries

**1. Register: Check email existence**
```python
stmt = select(User).where(User.email == req.email)
result = await db.execute(stmt)
if result.scalars().first() is not None:
    raise HTTPException(...)
```
**Assessment:** ✅ Optimal — uses indexed column, returns minimal data.

**2. Register: Insert user**
```python
new_user = User(email=req.email, password_hash=hashed)
db.add(new_user)
await db.commit()
```
**Assessment:** ✅ Standard ORM insert.

**3. Login: Lookup user by email**
```python
stmt = select(User).where(User.email == req.email)
result = await db.execute(stmt)
user = result.scalars().first()
```
**Assessment:** ✅ Optimal — indexed lookup, returns full User row for password verification.

**4. `get_current_user`: Lookup user by email**
```python
stmt = select(User).where(User.email == email)
result = await db.execute(stmt)
user = result.scalars().first()
```
**Assessment:** ⚠️ Identical to login query, runs on every API request.

### N+1 Query Risk

Currently no N+1 risk (single table, no relationships). When relationships are added, eager loading (`joinedload()`, `selectinload()`) should be used to avoid N+1 queries.

### Query Performance

With the existing schema (1 table, 1 index), all queries are:
- Single-table, single-predicate lookups
- Use the indexed `email` column
- Return single rows
- Execute in < 1ms on any modern PostgreSQL instance

---

## 11. Security & Configuration

### SSL Disabled

```python
connect_args={"ssl": False}  # database.py:26
```

**Issue:** Database connections are unencrypted. On any network path between the application and PostgreSQL, traffic can be intercepted, including:
- User email addresses
- Password hashes (bcrypt, but still transmitted)
- Session data (future)

### Credential Exposure

The `.env` file contains:
```
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/postgres
```

This connection string uses the `postgres` superuser account with no password. For local development this is acceptable, but the same `.env` file contains 9 live API keys.

### Config Validation Gap

```python
DATABASE_URL: str = Field(
    default="postgresql+asyncpg://user:password@localhost:5432/aetheris",
    validation_alias="DATABASE_URL",
)
```

The `DATABASE_URL` field has no validator. Invalid connection strings (wrong scheme, missing credentials) will fail at connection time, not at startup.

---

## 12. Issue Register

### DBA-001: No Database Migration System

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **File** | (project-wide) |
| **Lines** | — |
| **Description** | No Alembic configuration or migration scripts exist. Schema changes must be made via `Base.metadata.create_all` which only creates new tables and cannot alter existing ones. Production schema changes require manual SQL execution with no version tracking or rollback capability. |
| **Evidence** | No `alembic.ini`, no `migrations/` directory, no migration imports. `server.py:91-93`: `Base.metadata.create_all` is the only schema management mechanism. |
| **Impact** | Any schema change (adding columns, creating FK relationships, adding indexes) requires manual SQL in production. Cannot roll back failed changes. Team collaboration on schema changes is impossible. |
| **Root Cause** | Schema management was deferred during initial development. |
| **Suggested Resolution** | (1) Install Alembic: `pip install alembic`. (2) Run `alembic init migrations`. (3) Configure `alembic.ini` with the database URL. (4) Create initial migration from existing models. (5) Add migration creation to development workflow. (6) Add migration execution to deployment process. |
| **Verification** | Run `alembic history` — verify migration chain exists. Run `alembic upgrade head` — verify schema is created correctly. Add a new column to a model, run `alembic revision --autogenerate -m "add column"`, verify the migration file is correct. |

---

### DBA-002: Only One Database Model Exists

| Field | Value |
|-------|-------|
| **Severity** | High |
| **File** | `core/models.py` |
| **Lines** | 14-30 |
| **Description** | Only the `User` model exists. Sessions, checkpoints, conversations, telemetry, and provider health data are stored in-memory and lost on server restart. The database infrastructure is fully configured (async engine, pooling, session management) but only used for authentication queries. |
| **Evidence** | `core/models.py:14-30`: Only `User` class defined. `orchestrator/conversation.py:92`: `self._sessions: dict[str, ConversationSession]` — in-memory only. `orchestrator/checkpoints.py:257-259`: `raise NotImplementedError` for filesystem/database backends. |
| **Impact** | All non-auth application state is ephemeral. Server restart, deployment, or crash loses all conversation history, pipeline checkpoints, provider health data, and telemetry. |
| **Root Cause** | All persistent storage beyond auth was deferred to Phase 2. |
| **Suggested Resolution** | (1) Create `ConversationSession` and `ConversationMessage` models with FK → `users.id`. (2) Implement Checkpoint database backend using existing SQLAlchemy engine. (3) Create `ProviderHealthLog` model for historical provider metrics. (4) Create `TelemetryEntry` model for persistent telemetry. |
| **Verification** | After adding models, verify that: (1) Tables are created by migration. (2) Conversations survive server restart. (3) Checkpoints can be stored and retrieved from database. (4) Old data is cleaned up by background tasks. |

---

### DBA-003: No Connection Recycling

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `core/database.py` |
| **Lines** | 16-26 |
| **Function** | `create_async_engine` |
| **Description** | The database engine configuration does not set `pool_recycle`. Without connection recycling, connections idle longer than the database's `idle_in_transaction_session_timeout` or a network middlebox's timeout may be silently closed. The next query on that connection will fail with an error like "connection already closed". |
| **Evidence** | `database.py:16-26`: `pool_size=20`, `max_overflow=10`, `pool_pre_ping=True` — but no `pool_recycle` parameter. Default is `-1` (never recycle). |
| **Impact** | After periods of inactivity, connections may be stale. The application handles this partially via `pool_pre_ping=True`, but `pool_pre_ping` adds latency to every connection checkout. |
| **Root Cause** | Default configuration without tuning for deployment environment. |
| **Suggested Resolution** | Set `pool_recycle=3600` (recycle connections after 1 hour) to match common PostgreSQL and network middlebox timeouts. Add configuration via environment variable: `DATABASE_POOL_RECYCLE_SECONDS`. |
| **Verification** | Monitor connection pool metrics. After setting `pool_recycle=3600`, verify that connections older than 1 hour are recycled before being used. |

---

### DBA-004: No User Cache for Authentication Queries

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `core/security.py`, `server.py` |
| **Lines** | `security.py:340-367`, `server.py:309-339` |
| **Function** | `get_current_user`, `handle_query` |
| **Description** | Every authenticated API request executes a database query to fetch the User record by email. For endpoints with streaming responses, this database session is held for the duration of the stream. With the current pool size of 20, 20 concurrent streams would exhaust the pool. |
| **Evidence** | `security.py:361-363`: `stmt = select(User).where(User.email == email)` — runs on every API call. No `functools.lru_cache` or in-memory cache wrapping this query. SSE streaming endpoint (`server.py:309+`) uses `Depends(get_current_user)` which holds a DB session for the stream duration. |
| **Impact** | Pool exhaustion under concurrent streaming load. Unnecessary repeated queries for the same user data. |
| **Root Cause** | No caching layer was implemented. |
| **Suggested Resolution** | (1) Implement a short-TTL cache for `get_current_user` results (e.g., `functools.lru_cache` with 5-minute TTL). (2) For SSE streaming, release the DB session after authentication and before starting the stream. (3) Consider using a dedicated Redis cache if sessions are scaled horizontally. |
| **Verification** | After implementing cache, verify that: (1) 10 consecutive requests from the same user produce only 1 database query. (2) Cache is invalidated when user data changes. (3) SSE streams do not hold DB connections for their duration. |

---

### DBA-005: SSL Disabled for Database Connections

| Field | Value |
|-------|-------|
| **Severity** | High |
| **File** | `core/database.py` |
| **Lines** | 25 |
| **Function** | `create_async_engine` |
| **Description** | Database connections are explicitly configured without SSL: `connect_args={"ssl": False}`. All traffic between the application and PostgreSQL is transmitted in cleartext. On cloud deployments or cross-network configurations, this exposes credentials and data to interception. |
| **Evidence** | `database.py:25`: `connect_args={"ssl": False}`. No configuration option to enable SSL. |
| **Impact** | Credentials in the connection string (username, password) and all query results are transmitted without encryption. On any network path where packet capture is possible (shared cloud network, VPN, public network), data can be intercepted. |
| **Root Cause** | SSL was disabled for local development convenience and never re-enabled. |
| **Suggested Resolution** | (1) Change `connect_args={"ssl": False}` to read from configuration: `connect_args={"ssl": settings.DATABASE_SSL}`. (2) Default to `True` for production, allow `False` for local development. (3) Document the configuration option in deployment docs. |
| **Verification** | With SSL enabled, verify that: (1) Connection succeeds with proper certificate. (2) Wireshark/tcpdump shows encrypted traffic. (3) Connection fails when SSL is required but not configured on the server. |

---

### DBA-006: Database URL Contains Superuser Credentials

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `.env`, `core/config.py` |
| **Lines** | `.env:11`, `config.py:67-71` |
| **Description** | The `DATABASE_URL` uses the `postgres` superuser account with no password. The default configuration connects as the PostgreSQL superuser, which has unrestricted access to all databases and can perform administrative operations. |
| **Evidence** | `.env:11`: `DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/postgres`. Note: no password means the application connects without authentication. `config.py:67-71`: `default="postgresql+asyncpg://user:password@localhost:5432/aetheris"` — the default in config.py has a placeholder password but the .env overrides with the superuser account. |
| **Impact** | If the database is exposed to a network, any attacker with network access can connect as superuser. The application has full administrative database access when it only needs CRUD on specific tables. |
| **Root Cause** | Development convenience — using the default `postgres` superuser avoids separate user creation. |
| **Suggested Resolution** | (1) Create a dedicated application database user with minimal privileges: `CREATE USER aetheris_app WITH PASSWORD '...'; GRANT CONNECT ON DATABASE aetheris TO aetheris_app; GRANT USAGE, CREATE ON SCHEMA public TO aetheris_app;`. (2) Update `DATABASE_URL` in `.env` to use the restricted user. (3) Add a startup check that verifies the application user does not have superuser privileges. |
| **Verification** | After creating the restricted user, verify that: (1) The application connects and operates normally. (2) `SELECT current_user` returns `aetheris_app`, not `postgres`. (3) The application cannot execute `DROP TABLE` or other admin operations through the ORM. |

---

### DBA-007: No Connection Pool Monitoring

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `core/database.py` |
| **Lines** | 16-29 |
| **Description** | The database connection pool has no monitoring or metrics. Pool utilization, connection wait times, connection errors, and checkout times are not logged. Diagnosing pool exhaustion or connection issues requires manual inspection. |
| **Evidence** | No calls to `engine.pool.status()` or any pool monitoring. No logging of pool metrics. No FastAPI health check endpoint reports database connectivity. |
| **Impact** | Pool exhaustion causes silent request failures. Connection leaks are not detected until the pool is fully depleted. |
| **Root Cause** | Monitoring was not implemented — assumed sufficient for low-usage scenarios. |
| **Suggested Resolution** | (1) Add periodic logging of pool status: `pool.size()`, `pool.checkedin()`, `pool.overflow()`. (2) Add database connectivity check to health endpoint. (3) Log connection checkout times to detect slow queries or network issues. (4) Set up Prometheus metrics export for pool statistics. |
| **Verification** | After implementation, verify that: (1) Pool metrics appear in application logs. (2) Health endpoint reports database connectivity status. (3) Pool exhaustion triggers a warning log before blocking requests. |

---

### DBA-008: No Data Cleanup for Unused Models

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `core/models.py` |
| **Lines** | 14-30 |
| **Description** | The `User` model has no soft-delete capability, no `updated_at` timestamp, and no `is_active` flag. When users are deleted, there is no cascade mechanism. The background cleanup tasks (`background_tasks.py`) handle in-memory data but have no database cleanup routines. |
| **Evidence** | `models.py`: Only `id`, `email`, `password_hash`, `created_at` columns — no `updated_at`, `is_active`, `deleted_at`. `background_tasks.py`: Only cleans up conversations, checkpoints, graph patterns, and streams — no database cleanup. |
| **Impact** | User accounts cannot be deactivated (only hard-deleted from DB directly). No audit trail for account changes. When future models are added, orphaned data may accumulate. |
| **Root Cause** | User management was implemented at minimum viable level. |
| **Suggested Resolution** | (1) Add `updated_at` timestamp to User model. (2) Consider adding `is_active` boolean for account deactivation. (3) Add `deleted_at` for soft-delete support. (4) Create a database cleanup task that runs periodically. (5) For future models, always include `created_at` and `updated_at` timestamps. |
| **Verification** | After adding columns, verify that: (1) Existing users get default `updated_at` values. (2) User updates automatically set `updated_at`. (3) Soft-deleted users cannot log in. (4) Cleanup task correctly removes soft-deleted users after retention period. |

---

### DBA-009: No `get_db` Integration for SSE Endpoints

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `server.py` |
| **Lines** | ~460-540 |
| **Function** | SSE streaming endpoint |
| **Description** | The SSE streaming endpoint uses `Depends(get_current_user)` which creates a database session for the entire streaming duration. If the stream lasts 2+ minutes, the database connection is held for 2+ minutes. Multiple concurrent streams can exhaust the connection pool. |
| **Evidence** | The `/api/query/stream` handler accepts `current_user: User = Depends(get_current_user)`. The `get_db` dependency creates a session with `finally: await session.close()`. The session is only closed when the streaming response generator completes. |
| **Impact** | With 20 concurrent SSE streams, pool exhaustion occurs immediately (20 pool + potentially 10 overflow = 30 concurrent connections). New requests block waiting for connections. |
| **Root Cause** | The `get_db` FastAPI dependency pattern was applied uniformly without considering long-lived streaming connections. |
| **Suggested Resolution** | For SSE streaming: (1) Authenticate at route level (as currently). (2) Detach the DB session after authentication but before starting the SSH stream. (3) Do not use `get_db` for the stream body — instead, close the session and work without DB access for the stream duration. (4) If DB access is needed during streaming, create short-lived sessions as needed. |
| **Verification** | After refactoring, verify that: (1) Streaming requests do not consume database connections for the stream duration. (2) Authentication still works correctly. (3) Pool utilization during concurrent streaming stays well below pool size. |

---

## Summary Statistics

| Category | Issues | Critical | High | Medium | Low |
|----------|--------|----------|------|--------|-----|
| Schema & Models | 2 | 0 | 1 | 1 | 0 |
| Migrations | 1 | 1 | 0 | 0 | 0 |
| Connection Pooling | 2 | 0 | 0 | 1 | 1 |
| Caching | 1 | 0 | 1 | 0 | 0 |
| Security | 2 | 0 | 1 | 1 | 0 |
| Monitoring | 1 | 0 | 0 | 0 | 1 |
| **Total** | **9** | **1** | **3** | **3** | **2** |
