# AETHERIS Implementation Plan

**Plan Date:** 2026-06-27
**Author:** Principal Engineering Manager
**Scope:** Complete implementation roadmap for all 89 audit issues across 4 phases, with dependency graphs, milestones, and release readiness checklist.

---

## Table of Contents

1. [Phase Strategy](#1-phase-strategy)
2. [Phase 1 — Critical (Week 0–2)](#2-phase-1--critical-week-0-2)
3. [Phase 2 — High (Week 3–8)](#3-phase-2--high-week-3-8)
4. [Phase 3 — Medium (Week 9–14)](#4-phase-3--medium-week-9-14)
5. [Phase 4 — Low (Week 15–18)](#5-phase-4--low-week-15-18)
6. [Dependency Graphs](#6-dependency-graphs)
7. [Implementation Milestones](#7-implementation-milestones)
8. [Testing Milestones](#8-testing-milestones)
9. [Release Readiness Checklist](#9-release-readiness-checklist)
10. [Risk Register](#10-risk-register)

---

## 1. Phase Strategy

### Guiding Principles

1. **Security first**: All credential, authentication, and data exposure issues take Phase 1 priority
2. **Test before refactor**: Critical refactoring (CRIT-001) must not begin until test infrastructure exists (CRIT-002)
3. **Bottom-up dependency order**: Fix foundational layer issues before higher layers depend on them
4. **Observation then optimization**: Add monitoring and caching only after the baseline is stable
5. **Parallel tracks**: Infrastructure (Alembic, tests) runs in parallel with security fixes
6. **Low-risk first**: Within each phase, fix issues with no behavioral change before risky refactoring

### Phase Allocation by Severity

| Phase | Focus | Issues | Duration |
|-------|-------|--------|----------|
| **Phase 1** | Security & Infrastructure | 12 issues (7 CRIT + 5 HIGH) | 2 weeks |
| **Phase 2** | Architecture & Data | 17 issues (17 HIGH) | 6 weeks |
| **Phase 3** | Quality & Performance | 29 issues (29 MED) | 6 weeks |
| **Phase 4** | Polish & DX | 31 issues (31 LOW) | 4 weeks |

### Parallel Tracks

```
Week 0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18
├── Track A: Security fixes ───────────────────────────────
├── Track B: Tests ────────────────────────────────────────
├── Track C: Architecture ─────────────────────────────────
├── Track D: Data layer ───────────────────────────────────
├── Track E: Frontend ─────────────────────────────────────
└── Track F: Performance ──────────────────────────────────
```

---

## 2. Phase 1 — Critical (Week 0–2)

**Theme:** Stop active harm. Fix security vulnerabilities, rotate compromised credentials, establish test and migration infrastructure.

### Issue List (12 issues, sorted by implementation order)

---

#### P1-01: Rotate API Keys (CRIT-007 / HIGH-001)

| Field | Value |
|-------|-------|
| **Priority** | P0 — Immediate |
| **Dependencies** | None |
| **Estimated Time** | 2 hours (1 hour rotation + 1 hour cleanup) |
| **Risk** | Low — read-only change to `.env` |
| **Complexity** | Trivial |
| **Files to Modify** | `.env` (replace with empty strings), `.env.example` (ensure it exists) |
| **Validation Strategy** | (1) Verify each key is revoked at provider dashboard. (2) Run server in simulation mode — confirm no live API calls. (3) Verify `git diff` shows no key remnants. |
| **Regression Risk** | None — simulation mode activates when keys are empty; is a supported code path |

**Action items:**
1. Rotate all 9 keys at their respective provider dashboards (OpenRouter, NVIDIA, Groq, GitHub, Mistral, Google, OpenAI, Kie, UNLI.dev)
2. Replace key values in `.env` with `""` (empty string)
3. Verify `.env` is in `.gitignore`
4. Verify simulation mode works by running `main.py` without key file
5. Verify `.env.example` exists with documented placeholder values

---

#### P1-02: Fix CORS Configuration (CRIT-004)

| Field | Value |
|-------|-------|
| **Priority** | P0 — Immediate |
| **Dependencies** | None |
| **Estimated Time** | 2 hours |
| **Risk** | Low — breaks cross-origin access from unconfigured origins |
| **Complexity** | Trivial |
| **Files to Modify** | `server.py` (lines 148-154) |
| **Validation Strategy** | (1) Set `allow_origins` to `["http://localhost:5173", "http://localhost:8000"]` for dev. (2) Verify frontend API calls succeed. (3) Verify cross-origin requests from `http://evil.com` are blocked. |
| **Regression Risk** | Low — only affects CORS headers; no API logic changes |

**Implementation:**
```python
# Before
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
# After
origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
```

**Note:** `allow_credentials=True` with specific origins is valid per CORS spec.

---

#### P1-03: Harden JWT Secret Key (CRIT-005)

| Field | Value |
|-------|-------|
| **Priority** | P0 — Immediate |
| **Dependencies** | None |
| **Estimated Time** | 2 hours |
| **Risk** | Low — breaks token validation for existing sessions (force re-login) |
| **Complexity** | Trivial |
| **Files to Modify** | `core/config.py` (lines 73-77) |
| **Validation Strategy** | (1) Set `aetheris_JWT_SECRET_KEY` environment variable. (2) Verify login still works. (3) Verify old tokens are rejected. (4) Remove default — verify startup fails without env var set. |
| **Regression Risk** | Medium — all existing JWT tokens become invalid on deployment. Requires user re-login. Acceptable for production but requires communication. |

**Implementation:**
```python
# Before
JWT_SECRET_KEY: str = Field(default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
# After
JWT_SECRET_KEY: str = Field(default="", description="REQUIRED: Set via aetheris_JWT_SECRET_KEY env var")
```

Add startup validation:
```python
@field_validator("JWT_SECRET_KEY", mode="after")
@classmethod
def _reject_default_secret(cls, value: str) -> str:
    if not value or value == "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7":
        raise ValueError("JWT_SECRET_KEY must be set via aetheris_JWT_SECRET_KEY environment variable")
    return value
```

---

#### P1-04: Session/User Isolation (HIGH-015)

| Field | Value |
|-------|-------|
| **Priority** | P0 — Immediate |
| **Dependencies** | None (in-memory fix first; DB persistence in Phase 2) |
| **Estimated Time** | 1 day |
| **Risk** | Low — adds user ownership to existing in-memory sessions |
| **Complexity** | Low |
| **Files to Modify** | `orchestrator/conversation.py`, `server.py` |
| **Validation Strategy** | (1) Create user A session. (2) Verify user B cannot access it. (3) Verify user A can access and manage their own sessions. (4) Verify existing endpoints return 403 for unauthorized access. |
| **Regression Risk** | Low — session endpoints were not yet called by frontend; in-memory only |

**Implementation approach:**
1. Add `user_id: str | None` to `ConversationSession`
2. In `create_session`, require `user_id` parameter
3. Add authorization check in all session access methods: `session.user_id == current_user.id`

---

#### P1-05: Database SSL Configuration (HIGH-016)

| Field | Value |
|-------|-------|
| **Priority** | P0 — Immediate |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Low — may break existing connections if SSL not configured on PostgreSQL |
| **Complexity** | Low |
| **Files to Modify** | `core/database.py` (line 25), `core/config.py` |
| **Validation Strategy** | (1) Set `DATABASE_SSL=true` in environment. (2) Verify connection succeeds if PostgreSQL has SSL. (3) Set `DATABASE_SSL=false` for local dev — verify backward compatibility. |
| **Regression Risk** | Low — controlled via configuration; defaults to off for local dev |

**Implementation:**
```python
# config.py
DATABASE_SSL: bool = Field(default=False, validation_alias="DATABASE_SSL")

# database.py
connect_args={"ssl": settings.DATABASE_SSL}
```

---

#### P1-06: Database Superuser Credentials (MED-027)

| Field | Value |
|-------|-------|
| **Priority** | P0 — Immediate |
| **Dependencies** | None |
| **Estimated Time** | 2 hours |
| **Risk** | Low — creating a restricted DB user is a standard operation |
| **Complexity** | Low |
| **Files to Modify** | `.env`, README/deployment docs |
| **Validation Strategy** | (1) Create `aetheris_app` user with limited privileges. (2) Update `DATABASE_URL`. (3) Verify app starts and auth endpoints work. (4) Verify `SELECT current_user` returns `aetheris_app`, not `postgres`. |
| **Regression Risk** | Low — same queries, different user credentials |

**SQL to create restricted user:**
```sql
CREATE USER aetheris_app WITH PASSWORD '<secure-password>';
GRANT CONNECT ON DATABASE aetheris TO aetheris_app;
GRANT USAGE, CREATE ON SCHEMA public TO aetheris_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aetheris_app;
```

---

#### P1-07: HTTPS/TLS Configuration (MED-022)

| Field | Value |
|-------|-------|
| **Priority** | P0 — Immediate |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Low — TLS configuration is standard; may require certificate provisioning |
| **Complexity** | Low |
| **Files to Modify** | `server.py`, `deployment.md` |
| **Validation Strategy** | (1) Generate self-signed cert for testing. (2) Configure uvicorn with SSL cert and key. (3) Verify HTTPS connections succeed. (4) Verify HTTP connections redirect or are rejected. |
| **Regression Risk** | Low — no API logic changes; only affects transport layer |

---

#### P1-08: Setup Alembic Migrations (CRIT-006)

| Field | Value |
|-------|-------|
| **Priority** | P1 — Week 1 |
| **Dependencies** | CRIT-004, CRIT-005, CRIT-007 (infrastructure) |
| **Estimated Time** | 2 days |
| **Risk** | Low — initialization only; no production data to migrate yet |
| **Complexity** | Low |
| **Files to Modify** | New: `alembic.ini`, `migrations/` directory. Modified: `requirements.txt` |
| **Validation Strategy** | (1) Run `alembic init migrations`. (2) Run `alembic revision --autogenerate -m "initial"`. (3) Verify migration produces correct DDL matching `User` model. (4) Run `alembic upgrade head` against fresh database. (5) Verify `users` table created with correct schema. |
| **Regression Risk** | None — new files, no existing code modified |

---

#### P1-09: Setup Test Infrastructure (CRIT-002)

| Field | Value |
|-------|-------|
| **Priority** | P1 — Week 1 |
| **Dependencies** | CRIT-006 (Alembic) — test DB setup needs migration workflow |
| **Estimated Time** | 3 days |
| **Risk** | Low — new files; test helpers don't modify production code |
| **Complexity** | Medium |
| **Files to Modify** | New: `tests/`, `pytest.ini`, `conftest.py` |
| **Validation Strategy** | (1) Run `pytest` — verify 0 tests fail. (2) Create first test (ExecutionPassport unit test). (3) Verify test coverage reporting. (4) Add CI script for test execution. |
| **Regression Risk** | None — test infrastructure is additive |

**Test infrastructure plan:**
1. Create `tests/` directory structure:
   ```
   tests/
   ├── conftest.py          # Fixtures: mock gateway, passport, etc.
   ├── test_passport.py     # ExecutionPassport tests
   ├── test_security.py     # SecurityValidator tests
   ├── test_conversation.py # ConversationDirector tests
   ├── test_state_machine.py# StateMachine tests
   ├── test_decision_engine.py # DecisionEngine tests
   ├── test_pipeline.py     # Pipeline integration tests
   └── test_schemas.py      # Pydantic model tests
   ```
2. Add `pytest.ini`:
   ```ini
   [pytest]
   testpaths = tests
   asyncio_mode = auto
   markers = unit, integration, slow
   ```
3. Add test dependencies: `pytest>=8.0.0`, `pytest-asyncio>=0.24.0`, `pytest-cov>=5.0.0`

---

#### P1-10: Rate Limiting on Auth Endpoints (HIGH-014)

| Field | Value |
|-------|-------|
| **Priority** | P1 — Week 1-2 |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Low — can be tuned per environment |
| **Complexity** | Low |
| **Files to Modify** | `server.py` (auth routes), add optional `slowapi` dependency or implement in-memory counter |
| **Validation Strategy** | (1) Send 10 rapid login requests. (2) Verify 429 after threshold (5 attempts/min). (3) Verify legitimate login works after rate limit window. |
| **Regression Risk** | Low — only affects login/register endpoints; configurable limits |

**Implementation approach:** Add `slowapi` middleware to FastAPI app, configured via env var:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

@router.post("/auth/login")
@limiter.limit("5/minute")
async def login_user(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    ...
```

---

#### P1-11: Auth Input Validation (MED-021)

| Field | Value |
|-------|-------|
| **Priority** | P1 — Week 2 |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Low — validation-only change; no behavioral impact for valid inputs |
| **Complexity** | Low |
| **Files to Modify** | `server.py` (auth routes), `core/validators.py` (optional) |
| **Validation Strategy** | (1) Try registering with password "a" — verify rejection. (2) Try registering with invalid email — verify rejection. (3) Try registering with valid data — verify success. |
| **Regression Risk** | Low — only invalid inputs affected |

---

#### P1-12: CSRF Protection (MED-019)

| Field | Value |
|-------|-------|
| **Priority** | P1 — Week 2 |
| **Dependencies** | CRIT-004 (CORS fix must be in place first) |
| **Estimated Time** | 1 day |
| **Risk** | Low — no existing CSRF protection, so adding it is purely additive |
| **Complexity** | Low |
| **Files to Modify** | `server.py` (middleware), `core/config.py` |
| **Validation Strategy** | (1) Verify `SameSite=Strict` on future cookie-based auth. (2) Verify `Origin`/`Referer` validation for POST endpoints. (3) Verify legitimate requests pass through. |
| **Regression Risk** | Low — additive middleware with no existing CSRF checks to break |

---

### Phase 1 Completion Criteria

- [ ] All 9 API keys rotated and emptied from `.env`
- [ ] CORS configured with explicit allowed origins
- [ ] JWT secret validated at startup; default removed
- [ ] Database SSL configurable from environment
- [ ] Restricted database user created
- [ ] Alembic migration system operational
- [ ] pytest test infrastructure ready with first 10+ tests passing
- [ ] Rate limiting active on auth endpoints
- [ ] Auth input validation (password strength, email format)
- [ ] CSRF protections in place
- [ ] TLS configuration documented and testable
- [ ] Session/user isolation implemented

---

## 3. Phase 2 — High (Week 3–8)

**Theme:** Architecture stabilization. Eliminate dead code, consolidate duplicates, fix data persistence, establish frontend-backend contract alignment.

### Issue List (17 issues, sorted by implementation order)

---

#### P2-01: Remove Legacy Pipeline Path (CRIT-001)

| Field | Value |
|-------|-------|
| **Priority** | P1 — Phase 2 Week 1 |
| **Dependencies** | CRIT-002 (tests must exist before refactoring), MED-014, MED-016, MED-015 |
| **Estimated Time** | 3 weeks |
| **Risk** | High — this is the largest refactoring in the plan. Touches the most critical file (1152 lines) |
| **Complexity** | High |
| **Files to Modify** | `orchestrator/pipelines.py`, `orchestrator/decisions.py`, `orchestrator/evaluation.py` |
| **Validation Strategy** | (1) Run full test suite before and after — 0 regressions. (2) Run both legacy and DecisionEngine paths through integration tests — identical results. (3) Remove legacy path — verify all pipeline tests pass with only DecisionEngine. |
| **Regression Risk** | High — core pipeline logic. Mitigate by keeping both paths for one sprint, running integration tests on both, then removing legacy |

**Implementation order:**
1. MED-016 first: Replace 7+ identical try/except blocks with `transition_conversation_to_failed()` helper
2. MED-015: Fix user query history recording
3. MED-014: Fix double conversation state transition
4. Extract shared utilities (claim extraction, result assembly) from both paths into helpers
5. Run DecisionEngine-only pipeline path in staging for 1 week
6. Remove legacy inline path (lines 122-444, 484-724)
7. Rename `_run_with_decision_engine` to `run_pipeline` and make it the sole entry point

---

#### P2-02: Consolidate SecurityValidationError (HIGH-002)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 1 |
| **Dependencies** | None |
| **Estimated Time** | 2 days |
| **Risk** | Low — one class is dead code; removal is safe |
| **Complexity** | Low |
| **Files to Modify** | `core/error_handlers.py` (remove duplicate), verify importers |
| **Validation Strategy** | (1) grep for `from core.error_handlers import SecurityValidationError` — verify no active imports. (2) Remove from `error_handlers.py`. (3) Run test suite. (4) Run full pipeline. |
| **Regression Risk** | Low — the `error_handlers.py` version is never imported |

---

#### P2-03: Handle Pipeline Scheduler Dead Code (HIGH-003)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 1-2 |
| **Dependencies** | CRIT-001 decision: if DecisionEngine path replaces legacy, PipelineScheduler is replaceable |
| **Estimated Time** | 2 days (evaluation) + 1 day (removal) |
| **Risk** | Low — module is never imported |
| **Complexity** | Low |
| **Files to Modify** | Option A: Remove `orchestrator/pipeline_scheduler.py`. Option B: Wire into execution path |
| **Validation Strategy** | (1) Verify no imports: `grep -r "pipeline_scheduler" *.py`. (2) If Option A: delete file. (3) Verify test suite and server start cleanly. |
| **Regression Risk** | None — module is dead code |

**Recommendation:** Option A (remove). The DecisionEngine provides the same functionality with fewer lines. If the PipelineScheduler has features not in DecisionEngine, extract them before removal.

---

#### P2-04: Fix Private Method Access (HIGH-004)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 2 |
| **Dependencies** | None |
| **Estimated Time** | 1 hour |
| **Risk** | Low — public equivalent exists |
| **Complexity** | Trivial |
| **Files to Modify** | `api_gateway/rate_limiter.py` (line 907) |
| **Validation Strategy** | (1) Replace `pool._get_state(provider_name)` with `pool.get_status(provider_name)`. (2) Verify error count is accessed from returned dict. (3) Run integration test with provider degradation. |
| **Regression Risk** | Low — `get_status()` returns the same data with more fields |

---

#### P2-05: Normalize Provider Paths (HIGH-005)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 2 |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Low — removes side effect; adds graceful error |
| **Complexity** | Low |
| **Files to Modify** | `server.py` (lines 99-101) |
| **Validation Strategy** | (1) Remove PostgreSQL auto-start logic. (2) Verify startup logs clear error on DB connection failure. (3) Verify documented PostgreSQL requirement in README. |
| **Regression Risk** | Low — auto-start was likely already failing silently on non-Windows systems |

---

#### P2-06: RuntimeEngine Integration (HIGH-009)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 2-3 |
| **Dependencies** | CRIT-001 (pipeline path simplification) |
| **Estimated Time** | 2 weeks |
| **Risk** | Medium — RuntimeEngine is 270 lines of untested contract enforcement code |
| **Complexity** | Medium |
| **Files to Modify** | `core/runtime.py`, `orchestrator/pipelines.py`, `api_gateway/rate_limiter.py` |
| **Validation Strategy** | (1) Unit test RuntimeEngine.execute_with_contracts in isolation. (2) Integrate as wrapper around `execute_with_fallback`. (3) Run integration tests — verify contract validation fires on violations. (4) Verify streaming events, security checks, and metrics tracking appear. |
| **Regression Risk** | Medium — adding a new wrapper layer around every provider call. Must ensure timeout, semaphore, and fallback behavior are preserved |

---

#### P2-07: Frontend-Backend Session Sync (HIGH-008)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 3-4 |
| **Dependencies** | HIGH-015 (session isolation), HIGH-017 (DB models), MED-007 (DB sessions) |
| **Estimated Time** | 3 weeks |
| **Risk** | High — changes both frontend and backend; breaking change for localStorage state |
| **Complexity** | High |
| **Files to Modify** | `orchestrator/conversation.py`, `server.py`, `aetheris-ui/src/store/useChatStore.js`, `aetheris-ui/src/api/client.js` |
| **Validation Strategy** | (1) Backend: persist sessions to database. (2) Frontend: add session creation on app load. (3) Frontend: fetch history from backend on session selection. (4) Legacy migration: import localStorage conversations into backend on first connection. |
| **Regression Risk** | High — conversation history is user-visible. Mitigate: roll out gradually, keep localStorage as fallback for Phase 2 |

---

#### P2-08: Implement Database Models (HIGH-017)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 3-4 |
| **Dependencies** | CRIT-006 (Alembic must be operational) |
| **Estimated Time** | 2 weeks |
| **Risk** | Medium — adding new models is safe; data migration (if any production data exists) requires care |
| **Complexity** | Medium |
| **Files to Modify** | `core/models.py` (new models), new migration scripts |
| **Validation Strategy** | (1) Create Alembic migration. (2) Apply to test database. (3) Verify all tables created with correct columns, types, and constraints. (4) Test CRUD operations for each new model. |
| **Regression Risk** | Low — additive; existing User model unchanged |

**Models to create (in order):**
1. `ConversationSession` (FK → users.id) — replaces in-memory sessions
2. `ConversationMessage` (FK → sessions.id) — message persistence
3. `Checkpoint` (FK → users.id) — replaces memory-only checkpoints
4. `TelemetryEvent` (FK → users.id) — persistent telemetry

---

#### P2-09: Implement Checkpoint Database Backend (CRIT-003)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 4-5 |
| **Dependencies** | HIGH-017 (Checkpoint model must exist) |
| **Estimated Time** | 1 week |
| **Risk** | Low — backend switch from memory to DB; API unchanged |
| **Complexity** | Medium |
| **Files to Modify** | `orchestrator/checkpoints.py`, `core/models.py` (Checkpoint model) |
| **Validation Strategy** | (1) Implement DB `_store_checkpoint`, `_retrieve_checkpoint`, `_list_checkpoints_impl`, `_expire_checkpoints_impl`. (2) Set `storage_backend="database"`. (3) Save checkpoint. (4) Restart server. (5) Retrieve checkpoint — must survive restart. |
| **Regression Risk** | Medium — checkpoint API consumers may be affected if return types change. Maintain backward compatibility |

---

#### P2-10: Fix Streaming Fire-and-Forget Tasks (HIGH-011)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 5 |
| **Dependencies** | None |
| **Estimated Time** | 2 days |
| **Risk** | Low — additive error handling; no behavioral change for success path |
| **Complexity** | Low |
| **Files to Modify** | `orchestrator/decisions.py` (lines 160-166, 174-181, 213-219, 289-295) |
| **Validation Strategy** | (1) Attach `add_done_callback` to each task. (2) Force streaming emit to fail — verify error is logged. (3) Verify pipeline continues on streaming failure (graceful degradation). |
| **Regression Risk** | Low — additive; no change to success path execution |

---

#### P2-11: Fix Semaphore Bug (HIGH-012)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 5 |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Medium — changes concurrency behavior; may affect throughput under load |
| **Complexity** | Low |
| **Files to Modify** | `api_gateway/rate_limiter.py` (lines 654-655, 712-717) |
| **Validation Strategy** | (1) Remove erroneous `release()` before `acquire()`. (2) Use `asyncio.Semaphore.acquire()` correctly. (3) Load test with 200 concurrent requests — verify concurrency stays at 100. (4) Verify no "RuntimeError: Semaphore released too many times". |
| **Regression Risk** | Medium — concurrency limit may become stricter. Previously the bug inflated permits, so this fix reduces maximum concurrency to the configured limit |

---

#### P2-12: Address localStorage JWT Storage (HIGH-013)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 5-6 |
| **Dependencies** | None (can be done independently) |
| **Estimated Time** | 1 week |
| **Risk** | High — changing token storage mechanism from localStorage to httpOnly cookies affects auth flow and CORS |
| **Complexity** | Medium |
| **Files to Modify** | `aetheris-ui/src/utils/auth.js`, `aetheris-ui/src/api/client.js`, `server.py` (auth response), `core/security.py` |
| **Validation Strategy** | (1) Backend sets JWT in httpOnly, Secure, SameSite=Strict cookie on login. (2) Frontend Axios no longer manually attaches Bearer token. (3) Verify login, API calls, and token refresh work. (4) Verify localStorage no longer stores token. |
| **Regression Risk** | High — fundamental auth mechanism change. Requires full auth flow retesting. Mitigate: keep localStorage token as fallback for one release cycle |

---

#### P2-13: XML Prompt Caching (HIGH-018)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 6 |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Low — caching is purely additive; cache eviction on SIGHUP |
| **Complexity** | Low |
| **Files to Modify** | `agents/prompt_manager.py` (lines 103-139) |
| **Validation Strategy** | (1) Add `functools.lru_cache(maxsize=1)` to `load_runtime_contracts`. (2) Verify first call takes normal time (~10ms). (3) Verify subsequent calls take < 1ms. (4) Change XML file — verify cache clears on SIGHUP. |
| **Regression Risk** | Low — caching is invisible to callers |

---

#### P2-14: Disable or Implement Claim Validation (HIGH-019)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 6-7 |
| **Dependencies** | CRIT-001 (claim extraction is duplicated in both paths) |
| **Estimated Time** | Option A: 1 day (disable). Option B: 2 weeks (implement) |
| **Risk** | Low — either removing a no-op or replacing a placeholder with real implementation |
| **Complexity** | Option A: Low. Option B: Medium |
| **Files to Modify** | `orchestrator/pipelines.py`, `orchestrator/claims.py` |
| **Validation Strategy** | Option A: (1) Remove claim extraction calls from pipeline. (2) Verify pipeline runs without claims. (3) Verify response no longer includes unverified_claims field. Option B: (1) Implement cross-referencing validation. (2) Verify claims are marked VERIFIED when agents agree. (3) Verify throughput improves or remains same. |
| **Regression Risk** | Low — claims are not user-facing (only in telemetry). Removal or replacement causes no visible change |

**Recommendation:** Option A (disable) for Phase 2. Re-implement with proper validation in Phase 3.

---

#### P2-15: Unused Prompts Cleanup (HIGH-006 / HIGH-007)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 7 |
| **Dependencies** | None |
| **Estimated Time** | 1 day |
| **Risk** | Low — removing dead code |
| **Complexity** | Low |
| **Files to Modify** | `agents/personas.py`, `core/schemas.py`, `prompts/system/` directory |
| **Validation Strategy** | (1) Move unused prompts to `prompts/system/archive/`. (2) Remove VERIFIER_PROMPT and SKEPTIC_PROMPT. (3) Remove SignalState. (4) Verify all existing tests pass. |
| **Regression Risk** | Low — dead code removal; no imports reference these |

---

#### P2-16: Implement Token Refresh (MED-020)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 7-8 |
| **Dependencies** | HIGH-013 (token storage approach) |
| **Estimated Time** | 2 days |
| **Risk** | Low — additive; refresh token already stored but unused |
| **Complexity** | Low |
| **Files to Modify** | `server.py`, `aetheris-ui/src/api/client.js` |
| **Validation Strategy** | (1) Add `/auth/refresh` backend endpoint. (2) Add 401 interceptor in Axios that attempts refresh. (3) Wait for token expiry (or reduce TTL for testing) — verify automatic refresh. (4) Verify refresh token rotation. |
| **Regression Risk** | Low — additive unless the interceptor logic is wrong. Test with short TTL first |

---

#### P2-17: Implement Role-Based Access Control (MED-023)

| Field | Value |
|-------|-------|
| **Priority** | P2 — Phase 2 Week 8 |
| **Dependencies** | CRIT-005 (JWT hardening), HIGH-015 (session isolation) |
| **Estimated Time** | 3 days |
| **Risk** | Low — additive; existing behavior unchanged for existing users |
| **Complexity** | Medium |
| **Files to Modify** | `core/models.py` (role column), `core/security.py` (JWT claims), `server.py` (route dependencies) |
| **Validation Strategy** | (1) Add `role` to User model — migration. (2) Add role claim to JWT. (3) Create `require_role("admin")` dependency. (4) Protect provider recovery endpoint with admin role. (5) Verify regular user gets 403. |
| **Regression Risk** | Low — new field with default value; existing users get default role |

---

### Phase 2 Completion Criteria

- [ ] Legacy pipeline path removed; DecisionEngine is sole execution path
- [ ] SecurityValidationError consolidated to one definition
- [ ] PipelineScheduler removed or wired in
- [ ] Private method access replaced with public API
- [ ] Hardcoded PostgreSQL paths removed
- [ ] RuntimeEngine integrated into pipeline execution
- [ ] Frontend and backend session state synchronized
- [ ] Database models for sessions, messages, checkpoints, telemetry created
- [ ] Checkpoint database backend operational
- [ ] All streaming fire-and-forget tasks have error handlers
- [ ] Semaphore bug fixed — concurrency limits enforced correctly
- [ ] JWT stored in httpOnly cookies (not localStorage)
- [ ] XML prompt loading cached (48x I/O reduction)
- [ ] Claim validation disabled or implemented
- [ ] Unused prompts and schemas cleaned up
- [ ] Token refresh mechanism functional
- [ ] Role-based access control implemented

---

## 4. Phase 3 — Medium (Week 9–14)

**Theme:** Code quality, performance optimization, UI hardening, concurrency fixes.

### Issue List (29 issues, sorted by implementation order)

---

#### P3-01 to P3-29: All MED Issues

| ID | Issue | Dependencies | Time | Complexity |
|----|-------|-------------|------|------------|
| MED-001 | Private function import `_build_frontend_payload` | CRIT-001 (pipeline refactoring) | 1h | Trivial |
| MED-002 | Mode not passed to stream pipeline | None | 1d | Low |
| MED-003 | Duplicate streaming emit in runtime.py | HIGH-009 (RuntimeEngine) | 1d | Low |
| MED-004 | Duplicate conversation state blocks | MED-016 (helper exists) | 1d | Low |
| MED-005 | Duplicate emit methods in streaming.py | None | 1d | Low |
| MED-006 | Claim validation placeholder | HIGH-019 (claim fix) | 1d | Low |
| MED-007 | In-memory session persistence (DB push) | HIGH-017 (DB models) | 2w | Medium |
| MED-008 | Duplicate login pages | None | 2d | Low |
| MED-009 | Placeholder embeddings | HIGH-019 (claim dependency) | 1w | Medium |
| MED-010 | Duplicate field mapping in schemas | None | 1d | Low |
| MED-011 | DI bypass in AsyncAPIGateway | None | 1d | Low |
| MED-012 | Fire-and-forget streaming tasks | HIGH-011 (same fix) | 1d | Low |
| MED-013 | Semaphore handling bug | HIGH-012 (same fix) | 1d | Low |
| MED-014 | Double conversation transition | CRIT-001 (pipeline) | 1d | Low |
| MED-015 | User query not added to history | CRIT-001 (pipeline) | 1d | Low |
| MED-016 | Transition helper not used | CRIT-001 (pipeline) | 1d | Low |
| MED-017 | Instruction reinforcement schema mismatch | None | 1d | Low |
| MED-018 | Provider health metrics endpoint | None | 2d | Low |
| MED-024 | React error boundary | None | 1d | Low |
| MED-025 | Database pool_recycle | None | 1h | Trivial |
| MED-026 | User cache for auth queries | None | 1d | Low |
| MED-028 | Full re-render during streaming | None | 3d | Medium |
| MED-029 | Graph/Timeline data computed when not visible | None | 1d | Low |
| MED-030 | Sequential fallback latency | None | 3d | Medium |
| MED-031 | Instruction reinforcement token waste | MED-017 (same file) | 1d | Low |
| MED-032 | Sequential model chain latency | MED-030 (related) | 3d | Medium |

### Phase 3 Implementation Order

**Week 9-10 (Code Quality Sprint):**
1. MED-016 → MED-004 → MED-014 → MED-015 (conversation state consistency)
2. MED-003 → MED-005 (streaming DRY)
3. MED-001 → MED-002 → MED-010 → MED-011 (clean up coupling)

**Week 10-11 (UI Hardening Sprint):**
1. MED-024 (React error boundary) — highest user-facing impact
2. MED-008 (duplicate login pages)
3. MED-028 (streaming re-render optimization)
4. MED-029 (lazy graph computation)

**Week 11-12 (Performance Sprint):**
1. MED-025 → MED-026 (database tuning)
2. MED-030 → MED-032 (fallback latency)
3. MED-031 → MED-017 (token waste)
4. MED-006 (claim validation — if not already done in Phase 2)

**Week 12-13 (Data Persistence Sprint):**
1. MED-007 (database-backed sessions)
2. MED-009 (real embeddings)
3. MED-018 (health metrics endpoint)

**Week 13-14 (Remaining MED):**
1. MED-012 → MED-013 (concurrency) — merged with HIGH-011/HIGH-012
2. Remaining stragglers

---

## 5. Phase 4 — Low (Week 15–18)

**Theme:** Polish, documentation, developer experience, accessibility.

### Issue List (31 issues)

| ID | Summary | Time | Complexity |
|----|---------|------|------------|
| LOW-001 | Telemetry uses print() | 30m | Trivial |
| LOW-002 | confidence_delta naming | Already correct | — |
| LOW-003 | score_a/score_b same value | 1d | Low |
| LOW-004 | Private _get_state access | 30m | Trivial |
| LOW-005 | Stale __pycache__ artifacts | 5m | Trivial |
| LOW-006 | Documentation folder structure | 1h | Trivial |
| LOW-007 | Hook registration validation | 1h | Trivial |
| LOW-008 | Hardcoded frontend constants | 1h | Trivial |
| LOW-009 | HTTP client pool never closed | 1d | Low |
| LOW-010 | StreamingManager sync | 1d | Low |
| LOW-011 | Runtime contracts no cache | 1d | Low |
| LOW-012 | Synthesizer fallback key | 1h | Trivial |
| LOW-013 | Unused system prompts | 1h | Trivial |
| LOW-014 | XML no schema validation | 1d | Low |
| LOW-015 | Judge ignores history param | 1d | Low |
| LOW-016 | Confidence round-trip precision | 1d | Low |
| LOW-017 | Load order verification not called | 1h | Trivial |
| LOW-018 | Missing structured logging | 2d | Low |
| LOW-019 | Breaker gets full contracts | 2d | Low |
| LOW-020 | buildGraphData eager computation | 1d | Low |
| LOW-021 | SSE buffer size limit | 1d | Low |
| LOW-022 | MC tab keyboard navigation | 1d | Low |
| LOW-023 | Heading hierarchy | 1d | Low |
| LOW-024 | Reduced motion override | 1d | Low |
| LOW-025 | Stage notification race | 1d | Low |
| LOW-026 | Connection pool monitoring | 1d | Low |
| LOW-027 | Soft-delete for User model | 1d | Low |
| LOW-028 | SSE stream DB connection hold | 1d | Low |
| LOW-029 | Sync I/O in async pipeline | 2d | Low |
| LOW-030 | Unbounded SSE buffer | 1d | Low |
| LOW-031 | All MC tabs rendered | 1d | Low |

### Phase 4 Implementation Order

**Week 15 (Quick Wins):**
LOW-005, LOW-006, LOW-007, LOW-008, LOW-012, LOW-013, LOW-017 — all sub-1-hour fixes

**Week 15-16 (Low-Hanging Code Quality):**
LOW-001, LOW-003, LOW-004, LOW-009, LOW-010, LOW-011

**Week 16-17 (Frontend Polish):**
LOW-020, LOW-021, LOW-022, LOW-023, LOW-024, LOW-025, LOW-030, LOW-031

**Week 17-18 (Developer Experience):**
LOW-014, LOW-015, LOW-016, LOW-018, LOW-019, LOW-026, LOW-027, LOW-028, LOW-029

---

## 6. Dependency Graphs

### Level 0 — No dependencies (can start immediately)

- **Phase 1:** CRIT-007, CRIT-004, CRIT-005, HIGH-016, MED-027, MED-022, HIGH-014, MED-021
- **Phase 2:** HIGH-002, HIGH-003, HIGH-004, HIGH-005, HIGH-011, HIGH-012, HIGH-018, HIGH-006, HIGH-007, MED-020
- **Phase 3:** MED-002, MED-005, MED-008, MED-010, MED-011, MED-017, MED-018, MED-024, MED-025, MED-026, MED-028, MED-029, MED-030, MED-031, MED-032
- **Phase 4:** All LOW issues

### Level 1 — Dependent on Level 0

- CRIT-006 (Alembic) → CRIT-004, CRIT-005 (infrastructure first)
- CRIT-002 (tests) → infrastructure (needs pytest.ini, test DB)
- MED-019 (CSRF) → CRIT-004 (CORS fixed first)
- HIGH-017 (DB models) → CRIT-006 (Alembic ready)
- HIGH-009 (RuntimeEngine) → CRIT-001 (pipeline path simplified)

### Level 2 — Dependent on Level 1

- CRIT-001 (pipeline refactor) → CRIT-002 (tests exist), MED-014, MED-015, MED-016
- CRIT-003 (checkpoint DB) → HIGH-017 (DB models)
- HIGH-008 (session sync) → HIGH-017 (DB models), HIGH-015 (session isolation), MED-007 (DB sessions)
- MED-030 (fallback latency) → None (independent)
- MED-032 (model chain) → None (independent)

### Level 3 — Dependent on Level 2

- MED-007 (session persistence) → HIGH-017 (DB models)

### Dependency Graph (Text)

```
Level 0                          Level 1                Level 2                Level 3
─────────                        ─────────              ─────────              ─────────
CRIT-007 (API keys) ──────────┐
CRIT-004 (CORS) ─────────────┼──────────→ CRIT-006 ──→ HIGH-017 ──→ CRIT-003
CRIT-005 (JWT secret) ───────┘              │                             │
HIGH-016 (DB SSL)                           │               ┌─────────────┘
MED-027 (DB user)                           │               ↓
MED-022 (HTTPS)                             │            MED-007 (DB sessions)
HIGH-014 (rate limit)                       │
MED-021 (auth validation)                   ↓
                                       CRIT-002 (tests) ──→ CRIT-001 (pipeline)
                                                              ↑
HIGH-011 (fire-and-forget) ──────────────────────────────────┘
HIGH-012 (semaphore) ────────────────────────────────────────┘
HIGH-002 (duplicate error)
HIGH-003 (pipeline_scheduler)
HIGH-004 (private method)
HIGH-005 (PostgreSQL paths)
HIGH-018 (XML caching)
HIGH-006/HIGH-007 (dead code)
MED-020 (token refresh) ────→ HIGH-013 (JWT storage)
HIGH-013 (localStorage JWT) ──┼───────────────────────────────────────────→ MED-023 (RBAC)
                              │
MED-019 (CSRF) ─────────────→┘

HIGH-008 (session sync) ────────────────────────────────────→ HIGH-017, HIGH-015, MED-007
HIGH-009 (RuntimeEngine) ───────────────────────────────────→ CRIT-001
```

---

## 7. Implementation Milestones

### Milestone M1: "Secure Foundation" (End of Week 2)

**Goal:** No live credentials in codebase, production-ready security posture.

| Deliverable | Acceptance Criteria |
|-------------|-------------------|
| All API keys rotated | No live keys in `.env`; simulation mode works |
| CORS hardened | Specific origins configured; cross-origin exploit blocked |
| JWT hardened | Default secret removed; startup validation enforces custom secret |
| Database SSL configurable | Controlled via env var; defaults to off for dev |
| Rate limiting on auth | 5 req/min per IP on login/register |
| Auth input validation | Password strength ≥ 8 chars; email format validated |
| CSRF protections | SameSite=Strict on cookies; Origin validation on POST |
| HTTPS documented | TLS configuration documented in deployment.md |
| Session/user isolation | Sessions scoped to user; cross-user access blocked |
| Database user restricted | `aetheris_app` user with limited privileges |
| Migration system | Alembic operational with initial migration |

### Milestone M2: "Testable Architecture" (End of Week 4)

**Goal:** Regression-safe refactoring enabled by test coverage.

| Deliverable | Acceptance Criteria |
|-------------|-------------------|
| Test infrastructure | `pytest.ini`, `conftest.py`, test directory structure |
| ExecutionPassport tests | 95%+ branch coverage |
| SecurityValidator tests | All injection patterns tested |
| ConversationDirector tests | State transitions, truncation, expiry |
| StateMachine tests | All valid/invalid transitions tested |
| DecisionEngine tests | Breaker gate, parallel gen, judge synthesis |
| Pipeline integration tests | Full micro-mode pipeline with mocks |
| CI integration | Tests run on commit |

### Milestone M3: "Clean Pipeline" (End of Week 8)

**Goal:** Single execution path, no dead code, RuntimeEngine active.

| Deliverable | Acceptance Criteria |
|-------------|-------------------|
| Dual paths removed | DecisionEngine is sole execution path |
| Deadline: Week 6 | — |
| SecurityValidationError consolidated | Single definition in core/security.py |
| PipelineScheduler removed | File deleted; no imports |
| Private method access fixed | Public API used everywhere |
| PostgreSQL auto-start removed | Graceful error on DB connection failure |
| RuntimeEngine integrated | All provider calls go through contract enforcement |
| XML prompt caching | 48x I/O reduction; cache cleared on SIGHUP |
| Claim extraction disabled | Removed from pipeline; 50-200ms saved per request |
| Unused prompts/schemas removed | Archive directory; clean namespace |
| Frontend-backend session sync | Server-authoritative sessions; localStorage fallback |
| Database models created | Sessions, messages, checkpoints, telemetry |
| Checkpoint DB backend | Survives restart |
| Streaming tasks handled | Error handlers attached to all create_task calls |
| Semaphore bug fixed | Concurrency correctly limited to 100 |
| JWT in httpOnly cookies | localStorage no longer stores tokens |
| Token refresh functional | Automatic refresh on 401 |

### Milestone M4: "Quality & Performance" (End of Week 14)

**Goal:** DRY codebase, performant pipeline, hardened UI.

| Deliverable | Acceptance Criteria |
|-------------|-------------------|
| All MED-xxx issues resolved | 29 issues closed |
| Conversation state DRY | 7+ duplicate blocks replaced with helper |
| Streaming DRY | Single emit path; duplicate methods deprecated |
| React error boundary | Catches render errors; shows fallback UI |
| Streaming UI optimized | Targeted re-renders; Sidebar/InputBox stable |
| Database sessions persistent | Sessions survive server restart |
| Real embeddings (ReasoningGraph) | Sentence-transformers or API-based |
| Provider health endpoint | Exposes circuit breaker state |
| Fallback latency optimized | Concurrent fallback for degraded providers |
| Token waste reduced | Instruction reinforcement role-aware |
| Graph/Timeline lazy | Only computed when panel is visible |

### Milestone M5: "Polish & DX" (End of Week 18)

**Goal:** Production-ready quality, accessibility, and developer experience.

| Deliverable | Acceptance Criteria |
|-------------|-------------------|
| All LOW-xxx issues resolved | 31 issues closed |
| All `print()` calls removed | Logger used everywhere |
| Documentation updated | README, architecture docs, deployment docs |
| Stale artifacts cleaned | No orphaned `.pyc` files |
| Keyboard navigation complete | All interactive elements accessible |
| Reduced motion compliant | All CSS animations respect preference |
| Structured logging consistent | All modules use `extra` fields |
| Connection pool monitored | Metrics logged periodically |
| SSE streams release DB | Sessions closed before streaming starts |
| Async I/O in executors | Blocking file/CPU ops moved off event loop |

---

## 8. Testing Milestones

### Test Milestone T1: Infrastructure Week (End of Week 1)

| Test Area | Count | Type | Owner |
|-----------|-------|------|-------|
| pytest configuration | 1 | Infrastructure | Backend |
| conftest fixtures | 5+ | Reusable | Backend |
| First passing test | 1 | Sanity | Backend |

### Test Milestone T2: Core Components (End of Week 3)

| Test Area | Count | Type | Coverage Target |
|-----------|-------|------|-----------------|
| ExecutionPassport | 20+ | Unit | 95% branch |
| SecurityValidator | 30+ | Unit | 95% branch |
| ConversationDirector | 25+ | Unit | 90% branch |
| StateMachine | 15+ | Unit | 100% branch |
| Pydantic schemas | 20+ | Unit | 95% line |
| **Cumulative** | **110+** | | |

### Test Milestone T3: Pipeline & Decision Engine (End of Week 5)

| Test Area | Count | Type | Coverage Target |
|-----------|-------|------|-----------------|
| DecisionEngine | 30+ | Unit + Integration | 90% branch |
| ProviderPool | 25+ | Unit | 90% branch |
| ResourceManager | 20+ | Unit | 90% branch |
| StreamingManager | 20+ | Unit | 90% branch |
| MemoryManager | 15+ | Unit | 90% branch |
| Pipeline integration | 10+ | Integration | All paths |
| CheckpointManager | 15+ | Unit | 90% branch |
| **Cumulative** | **245+** | | |

### Test Milestone T4: Full Backend (End of Week 8)

| Test Area | Count | Type | Coverage Target |
|-----------|-------|------|-----------------|
| ClaimManager | 15+ | Unit | 90% branch |
| ReasoningGraph | 20+ | Unit | 90% branch |
| RuntimeEngine | 20+ | Unit | 95% branch |
| State machine + pipeline | 10+ | Integration | All paths |
| Auth end-to-end | 10+ | Integration | Login, register, token refresh |
| **Cumulative** | **320+** | | |

### Test Milestone T5: Frontend (End of Week 10)

| Test Area | Count | Type | Coverage Target |
|-----------|-------|------|-----------------|
| Auth flows | 10+ | Unit + Integration | Token storage, refresh, logout |
| API client | 15+ | Unit | SSE parsing, retry, error handling |
| Session sync | 10+ | Integration | Backend session → frontend state |
| **Cumulative** | **355+** | | |

### Test Milestone T6: Performance & Regression (End of Week 14)

| Test Area | Count | Type | Coverage Target |
|-----------|-------|------|-----------------|
| Performance benchmarks | 10+ | Integration | Latency, throughput, memory |
| Load tests | 5+ | Integration | Concurrency, pool behavior |
| Full regression suite | Full | All | All component tests |
| **Cumulative** | **380+** | | |

### Final Test Targets

| Metric | Target |
|--------|--------|
| **Total tests** | 400+ |
| **Backend line coverage** | 85%+ |
| **Frontend line coverage** | 75%+ |
| **Integration tests** | 30+ (full pipeline with mocks) |
| **Load tests** | 5+ (concurrent users, pool behavior) |
| **CI runtime** | < 10 minutes |

---

## 9. Release Readiness Checklist

### Pre-Release Gate Check

#### Security
- [ ] All API keys are environment-configured, not in source
- [ ] JWT secret is set via environment, validated at startup
- [ ] CORS origins are explicitly configured (not `*`)
- [ ] Database connections use SSL (configurable)
- [ ] Auth endpoints are rate-limited
- [ ] Passwords meet strength requirements
- [ ] CSRF protections are active
- [ ] TLS is configured or documented as required
- [ ] No secrets in logs (scrub patterns verified)
- [ ] Session/user isolation verified

#### Architecture
- [ ] Single pipeline execution path (no legacy code)
- [ ] No dead code modules (pipeline_scheduler removed)
- [ ] No duplicate exception classes
- [ ] Layering violations fixed (core does not import orchestration)
- [ ] No private functions imported cross-module

#### Data
- [ ] Alembic migrations exist for all models
- [ ] Database-backed sessions survive restart
- [ ] Database-backed checkpoints survive restart
- [ ] Connection pool properly configured
- [ ] Database user has restricted privileges
- [ ] Soft-delete or deactivation for user accounts

#### Testing
- [ ] Test suite passes (400+ tests)
- [ ] Line coverage ≥ 85% (backend)
- [ ] Integration tests for full pipeline
- [ ] Load tests pass (100 concurrent requests)
- [ ] CI/CD pipeline includes test execution

#### Performance
- [ ] XML prompt caching active
- [ ] Claim extraction no longer runs as no-op
- [ ] Streaming fire-and-forget tasks have error handlers
- [ ] Semaphore correctly limits concurrency
- [ ] RuntimeEngine contract enforcement active
- [ ] Concurrent provider fallback available
- [ ] Frontend renders efficiently during streaming

#### Frontend
- [ ] React error boundary present
- [ ] Token refresh mechanism functional
- [ ] JWT stored securely (httpOnly cookie or documented exception)
- [ ] Duplicate login pages consolidated
- [ ] Keyboard navigation across all components
- [ ] Accessibility heading hierarchy
- [ ] Reduced motion preference respected
- [ ] SSE events render without excessive re-renders

#### Monitoring
- [ ] Connection pool metrics logged
- [ ] Provider health endpoint exposes circuit breaker state
- [ ] Structured logging with correlation IDs
- [ ] Telemetry export functional
- [ ] Health check endpoint includes database connectivity

### Release Sign-off

| Role | Sign-off Criteria |
|------|-------------------|
| **Security** | All security checklist items verified; penetration test passed |
| **Engineering** | All Phases 1-3 complete; regression suite passes |
| **QA** | 400+ tests passing; load tests within threshold |
| **Product** | Key user flows tested (login, query, streaming, settings) |
| **Documentation** | All docs updated; deployment guide verified |

---

## 10. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Pipeline refactor (CRIT-001) breaks production | Medium | High | Keep both paths for 1 sprint; run integration tests on both; remove only after verification |
| JWT cookie migration (HIGH-013) breaks auth for existing users | Medium | High | Keep localStorage fallback for 1 release; migrate gradually; communicate outage window |
| CORS fix blocks frontend development | Low | Medium | Configure multiple localhost origins; document CORS_ORIGINS env var |
| Database migration causes data loss | Low | Critical | Test migrations on staging first; backup production DB before upgrade; practice rollback |
| Concurrent fallback (MED-030) increases API costs | Low | Medium | Implement as opt-in configuration; default to sequential for non-critical paths |
| Test infrastructure delays Phase 2 start | Medium | Medium | Start test infrastructure in parallel with Phase 1 security fixes |
| Performance degradation from RuntimeEngine integration | Low | Medium | Benchmark before and after; keep bypass path for latency-critical calls |
| Team capacity insufficient for 18-week plan | Medium | High | Prioritize Phase 1+2 as minimum for MVP; defer Phase 4 to post-launch |

---

## Appendix: Issue Priority Mapping

| Priority | Issues | Criteria |
|----------|--------|----------|
| **P0 — Emergency** | CRIT-007, CRIT-004, CRIT-005, HIGH-016, MED-027, MED-022 | Active security vulnerability or data exposure |
| **P1 — Critical** | CRIT-006, CRIT-002, HIGH-014, HIGH-015, MED-019, MED-021 | Infrastructure or access control gaps |
| **P2 — High** | CRIT-001, CRIT-003, HIGH-002, HIGH-003, HIGH-004, HIGH-005, HIGH-008, HIGH-009, HIGH-011, HIGH-012, HIGH-013, HIGH-017, HIGH-018, HIGH-019, HIGH-006, HIGH-007, MED-020, MED-023 | Architecture, data, or process integrity |
| **P3 — Medium** | All 29 MED issues | Code quality, performance, hardening |
| **P4 — Low** | All 31 LOW issues | Polish, DX, documentation |
