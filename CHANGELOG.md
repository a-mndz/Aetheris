# Changelog

All notable changes to the AETHERIS project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — Planned Changes

### Phase 1 — Critical (Week 0-2)

#### Security — Emergency
- **CRIT-007/HIGH-001**: Rotate 9 exposed API keys across all providers. Replace live keys in `.env` with empty strings. Activate simulation mode as fallback.
- **CRIT-004**: Restrict CORS from wildcard (`*`) to explicit origins via `CORS_ORIGINS` environment variable. Fix `allow_credentials=True` + wildcard violation.
- **CRIT-005**: Remove hardcoded default JWT secret key from `core/config.py`. Add startup validation requiring `aetheris_JWT_SECRET_KEY` environment variable.
- **HIGH-014**: Add rate limiting to `/auth/login` and `/auth/register` endpoints (5 req/min per IP).
- **MED-027**: Create restricted database user `aetheris_app` with limited privileges. Update `DATABASE_URL`. Remove superuser credential.
- **HIGH-016**: Make database SSL configurable via `DATABASE_SSL` environment variable. Default to `false` for local development.
- **MED-022**: Add TLS/SSL configuration support. Document in deployment guide.
- **MED-021**: Add password strength validation (minimum 8 characters, complexity) and email format validation to registration endpoint.
- **MED-019**: Add CSRF protection middleware. Set `SameSite=Strict` on auth cookies. Add `Origin`/`Referer` validation for POST endpoints.
- **HIGH-015**: Add user ownership to conversation sessions. Implement authorization checks for cross-user session access.

#### Infrastructure
- **CRIT-006**: Initialize Alembic migration system. Create initial migration from existing `User` model. Configure `alembic.ini`.
- **CRIT-002**: Create `tests/` directory with pytest configuration. Implement test infrastructure with `conftest.py`, fixtures, and CI integration. Write first test batch (ExecutionPassport, SecurityValidator, ConversationDirector, StateMachine — 110+ tests).

---

### Phase 2 — High (Week 3-8)

#### Architecture
- **CRIT-001**: Remove legacy inline pipeline path from `orchestrator/pipelines.py`. Consolidate to single DecisionEngine path. Extract shared utilities (conversation handling, claim extraction, result assembly) from duplicated code. Rename `_run_with_decision_engine` to `run_pipeline` as sole entry point.
- **HIGH-002**: Remove duplicate `SecurityValidationError` from `core/error_handlers.py`. Consolidate to single definition in `core/security.py`.
- **HIGH-003**: Remove dead `orchestrator/pipeline_scheduler.py` module (679 lines, never imported).
- **HIGH-004**: Replace private method access `pool._get_state()` with public `pool.get_status()`.
- **HIGH-005**: Remove PostgreSQL auto-start logic from `server.py`. Replace with graceful error message on connection failure.
- **HIGH-006/HIGH-007**: Move unused `VERIFIER_PROMPT`, `SKEPTIC_PROMPT`, and `SignalState` to archive. Remove from active namespace.

#### Contract Enforcement
- **HIGH-009**: Integrate `RuntimeEngine.execute_with_contracts` into pipeline execution path. All provider calls now pass through security validation, streaming, rate limiting, and metrics tracking.
- **HIGH-011**: Attach error handlers (`add_done_callback`) to all fire-and-forget `asyncio.create_task` calls in DecisionEngine streaming events.
- **HIGH-012**: Fix semaphore handling bug in `ResourceManager.acquire_resources`. Remove erroneous release-before-acquire pattern.

#### Data Layer
- **HIGH-017**: Create database models for `ConversationSession`, `ConversationMessage`, `Checkpoint`, and `TelemetryEvent`. Create Alembic migrations for all new models.
- **CRIT-003**: Implement database storage backend for `CheckpointManager`. Replace `NotImplementedError` with SQLAlchemy-based persistence.
- **MED-007**: Migrate `ConversationDirector` sessions from in-memory dict to database-backed storage.
- **MED-025**: Add `pool_recycle=3600` to SQLAlchemy engine configuration.

#### Frontend Auth
- **HIGH-013**: Migrate JWT storage from `localStorage` to `httpOnly` secure cookies with `SameSite=Strict`. Update Axios interceptors to use cookie-based auth. Remove manual Bearer token attachment.
- **MED-020**: Implement token refresh mechanism. Add `/auth/refresh` backend endpoint. Add automatic refresh in Axios 401 interceptor.
- **MED-023**: Add `role` field to User model. Add role claim to JWT. Create `require_role()` FastAPI dependency. Protect provider recovery endpoint with admin role.

#### Frontend-Backend Integration
- **HIGH-008**: Synchronize frontend and backend session management. Add session creation on app load. Fetch history from backend on session selection. Keep localStorage as fallback cache.

#### Performance
- **HIGH-018**: Add `functools.lru_cache` to `load_runtime_contracts`. Eliminate 48 file I/O ops per request.
- **HIGH-019**: Disable claim extraction in pipeline pipeline (placeholder validation produces no value). Save 50-200ms per request.

---

## [Phase 2 — Verified 2026-06-28] — Platform Completion

Phase 1 stabilised the engineering core.  Phase 2 closes the remaining
High-priority items deferred from Phase 1 and resolves the backlog of
Medium and Low items called out in the audit.  Full Phase 2 ledger:
see `docs/repair/REPAIR_LEDGER.md` for entries `REP-001001`…
`REP-001007`.

### Architecture — Dead Code & Cleanup (HIGH-003 / HIGH-006 / HIGH-007)
- `orchestrator/pipeline_scheduler.py` deleted (HIGH-003, 679 lines, was never imported).
- `VERIFIER_PROMPT` and `SKEPTIC_PROMPT` removed from `PERSONA_REGISTRY` (HIGH-006; archived mention retained in module-level comment).
- `core.schemas.SignalState` class removed (HIGH-007).

### Conversation State Consolidation (MED-004 / MED-015 / MED-016)
- New `orchestrator.pipelines._mark_conversation_failed` helper replaces
  nine identical `try/except` blocks (was ~63 lines of duplication,
  now ~17 lines + 9 single-line call sites).
- New `agents.prompt_utils.record_user_query` helper records the user's
  query as a history turn in `run_micro_mode` and `stream_micro_mode`.

### Data Persistence (CRIT-003)
- `CheckpointManager` now persists to PostgreSQL via `CheckpointRecord`
  when `storage_backend="database"` and a session factory are provided.
  Memory backend behaviour preserved; new helpers
  `_store_checkpoint_db`, `_retrieve_checkpoint_db`,
  `_list_checkpoints_db`, `_expire_checkpoints_db`.

### Authentication — RBAC + Token Refresh (MED-020 / MED-023)
- New `core.security.require_role("admin")` FastAPI dependency protects
  `/api/providers/health` and `/api/providers/{provider}/recovery`.
- New `/auth/refresh` endpoint; front-end `refreshAccessToken()` is
  invoked from the axios response interceptor on 401.

### Frontend — Cookie Auth Phased Rollout
- `apiClient` now sets `withCredentials: true` so the httpOnly cookie is
  sent on every authenticated request; `Authorization: Bearer` still
  rides in for the legacy localStorage fallback.

### Misc Fixes
- `F841`: dropped unused `result = ` assignment in `CheckpointManager.save_checkpoint`.
- Tests: 18 new backend tests, all 327 backend + frontend tests pass.

---

### Phase 3 — Medium (Week 9-14)

#### Code Quality — Conversation State
- **MED-016**: Replace 7+ identical try/except blocks with `transition_conversation_to_failed()` helper.
- **MED-004**: Apply MED-016 fix to all pipeline paths.
- **MED-014**: Fix double conversation state transition in DecisionEngine path.
- **MED-015**: Add user query turn to conversation history.

#### Code Quality — Streaming
- **MED-003**: DRY up duplicate streaming event construction in `RuntimeEngine`.
- **MED-005**: Deprecate `emit` and `emit_raw` methods. Consolidate to single `emit_event` path.

#### Code Quality — Coupling
- **MED-001**: Rename `_build_frontend_payload` → `build_frontend_payload` and export from public API.
- **MED-002**: Plumb mode parameter through `stream_micro_mode` to respect configured strategy.
- **MED-010**: Extract shared field-mapping logic into `core/validators.resolve_field`.
- **MED-011**: Wire dependencies through constructor injection in `main.py` and `server.py`.

#### UI Hardening
- **MED-024**: Add React error boundary class component wrapping entire app. Show fallback UI with reload button on render errors.
- **MED-008**: Consolidate duplicate login pages into a single React component within Vite build pipeline.
- **MED-028**: Split streaming state into dedicated context. Use Zustand selectors for fine-grained subscriptions. Memoize non-streaming components.
- **MED-029**: Move graph and timeline data computation into MissionControlPanel. Compute only when relevant tab is active.

#### Performance — Provider
- **MED-030**: Implement concurrent provider fallback using `asyncio.gather` with `return_exceptions=True`.
- **MED-032**: Apply concurrent fallback strategy across all model chains.
- **MED-017**: Make instruction reinforcement role-aware — different schema reminder for Judge vs generation agents.
- **MED-031**: Reduce instruction reinforcement token waste by making it conditional and schema-correct.

#### Data & Knowledge
- **MED-009**: Replace placeholder character-frequency embeddings in ReasoningGraph with sentence-transformers or API-based semantic embeddings.
- **MED-006**: Implement basic claim cross-referencing validation between agents, or disable if not providing value.

#### Monitoring
- **MED-018**: Add `GET /api/providers/health` endpoint exposing ProviderPool circuit breaker state, error rates, and cooldown status.
- **MED-026**: Implement short-TTL in-memory cache for `get_current_user` to reduce database queries.

---

### Phase 4 — Low (Week 15-18)

#### Quick Wins
- **LOW-001**: Replace `print()` calls with `logger.info()` in TelemetryObserver.
- **LOW-003**: Rename `score_a`/`score_b` to `logician_score`/`creative_score`.
- **LOW-004**: Replace `pool._get_state()` with `pool.get_status()`.
- **LOW-005**: Delete orphaned `.pyc` files from deleted modules.
- **LOW-006**: Update README directory structure reference.
- **LOW-007**: Add `Callable[[], None]` type validation to `register_hook`.
- **LOW-008**: Move hardcoded constants to Vite environment variables.
- **LOW-011**: Add `functools.lru_cache` to `load_runtime_contracts` (complement to HIGH-018).
- **LOW-012**: Fix synthesizer fallback key in `PERSONA_REGISTRY`.
- **LOW-013**: Archive unused system prompt XML files.
- **LOW-017**: Call `get_load_order_verification()` during startup.

#### Developer Experience
- **LOW-009**: Add lifecycle hooks to close HTTP client connection pool on shutdown.
- **LOW-010**: Add synchronization to StreamingManager dict accesses.
- **LOW-014**: Add structural XML validation beyond well-formedness.
- **LOW-015**: Wire conversation `history` into judge synthesis prompt.
- **LOW-016**: Fix confidence round-trip precision (float→score×10→score/10).
- **LOW-018**: Add structured logging (`extra` fields with request_id, stage) to pipeline and decision engine modules.
- **LOW-019**: Implement role-specific contract selection for Breaker (reduce context).
- **LOW-026**: Add periodic logging of database connection pool metrics.
- **LOW-027**: Add `updated_at` and `is_active` columns to User model.
- **LOW-028**: Detach DB session after authentication for SSE streaming endpoints.
- **LOW-029**: Move synchronous I/O and CPU-bound operations to asyncio thread pool executor.

#### Frontend Polish
- **LOW-020**: Move graph data computation into MissionControlPanel (lazy evaluation).
- **LOW-021**: Add maximum buffer size limit (1MB) to SSE parser.
- **LOW-022**: Add keyboard arrow navigation for Mission Control tabs (WAI-ARIA tabs pattern).
- **LOW-023**: Add heading hierarchy (`h1`–`h6`) across the application.
- **LOW-024**: Complete CSS reduced-motion override with `animation-play-state: paused`.
- **LOW-025**: Fix pipeline stage notification race condition.
- **LOW-030**: Add defensive upper bound on SSE buffer accumulation.
- **LOW-031**: Render only active Mission Control tab; unmount hidden tabs.

---

## Phase Completion Checklist

### Phase 1 ✅ (Target: End of Week 2)
- [ ] CRIT-007: API keys rotated and emptied
- [ ] CRIT-004: CORS origins configured
- [ ] CRIT-005: JWT secret hardened
- [ ] CRIT-006: Alembic migration system ready
- [ ] CRIT-002: Test infrastructure with 110+ tests
- [ ] HIGH-014: Rate limiting on auth endpoints
- [ ] HIGH-015: Session/user isolation
- [ ] HIGH-016: Database SSL configurable
- [ ] MED-019: CSRF protection
- [ ] MED-021: Auth input validation
- [ ] MED-022: HTTPS configuration support
- [ ] MED-027: Restricted database user

### Phase 2 ✅ (Target: End of Week 8)
- [ ] CRIT-001: Single pipeline path
- [ ] CRIT-003: Checkpoint database backend
- [ ] HIGH-002: Duplicate exception removed
- [ ] HIGH-003: Dead pipeline_scheduler removed
- [ ] HIGH-004: Private method access fixed
- [ ] HIGH-005: PostgreSQL auto-start removed
- [ ] HIGH-006/HIGH-007: Dead code cleaned
- [ ] HIGH-008: Frontend-backend session sync
- [ ] HIGH-009: RuntimeEngine integrated
- [ ] HIGH-011: Streaming error handlers
- [ ] HIGH-012: Semaphore bug fixed
- [ ] HIGH-013: JWT stored in httpOnly cookies
- [ ] HIGH-017: Database models for all entities
- [ ] HIGH-018: XML prompt caching
- [ ] HIGH-019: Claim waste eliminated
- [ ] MED-020: Token refresh implemented
- [ ] MED-023: RBAC implemented

### Phase 3 ✅ (Target: End of Week 14)
- [ ] MED-001 through MED-032: All resolved
- [ ] 380+ tests passing
- [ ] 85%+ backend coverage
- [ ] No duplicate streaming or state patterns
- [ ] Error boundary protecting entire UI
- [ ] Streaming renders optimized
- [ ] Concurrent fallback available
- [ ] Provider health endpoint active
- [ ] User record caching operational

### Phase 4 ✅ (Target: End of Week 18)
- [ ] LOW-001 through LOW-031: All resolved
- [ ] 400+ tests passing
- [ ] Documentation fully updated
- [ ] Keyboard navigation complete
- [ ] Accessibility compliance verified
- [ ] Reduced motion respected
- [ ] Structured logging everywhere
- [ ] Async I/O in executors
- [ ] Database pool monitored

---

## Version History

### [0.1.0] — Pre-Audit
- Initial AETHERIS implementation
- 89 audit issues identified across architecture, security, database, frontend, and performance

### [1.0.0] — Planned
- Phase 1-4 completion target: Week 18
- All 89 audit issues resolved
- 400+ unit and integration tests
- 85%+ backend test coverage

---

## Appendix: Issue Migration Guide

| Previous Storage | Target Storage | Phase | Key File |
|-----------------|----------------|-------|----------|
| ConversationDirector._sessions (dict) | conversation_sessions table | Phase 2/3 | `core/models.py` |
| Conversation history (dict) | conversation_messages table | Phase 2/3 | `core/models.py` |
| CheckpointManager.checkpoints (dict) | checkpoints table | Phase 2 | `core/models.py` |
| TelemetryObserver (singleton) | telemetry_events table | Phase 2 | `core/models.py` |
| EpistemicMemory.failed_loops (deque) | failure_patterns table | Phase 3 | `core/models.py` |
| ProviderPool._providers (dict) | provider_health_log table | Phase 3 | `core/models.py` |
| ReasoningGraph._nodes/_edges (dict) | knowledge_graph tables | Phase 4 | `core/models.py` |
| localStorage (conversations) | Backend session API | Phase 2 | `server.py` |
| localStorage (JWT) | httpOnly cookies | Phase 2 | `core/security.py` |
# Changelog â€” Phase 1 Releases

> Append-only history of post-audit Phase 1 changes, 2026-06-27.

---

## [0.2.0] â€” 2026-06-27 â€” Phase 1 â€” Core Stabilization âœ…

### Security â€” Emergency (P0)

- **CRIT-004** (`core/config.py`, `server.py`): CORS wildcard with credentials replaced
  by explicit `CORS_ORIGINS` allowlist. `_resolve_cors_origins()` rejects `*` and
  missing origins. Authentication middleware parses `Origin` / `Referer` headers and
  rejects POST/PUT/DELETE/PATCH whose origin is not in the allowlist (CSRF).
- **CRIT-005** (`core/config.py`): Hardcoded default JWT secret removed. `aetherisConfig`
  enforces: rejection of empty, the canonical demo fallback, and any secret under
  32 characters. Operators MUST rotate existing secret before first deploy.
- **CRIT-007** (`core/config.py`): pydantic `field_validator` rejects any provider
  key matching live prefixes (`sk-or-v1-`, `nvapi-`, `gsk_p`, `github_pat_`,
  `sk-proj-`, `sk-ZO`, `AQ.Ab8`). The committed `.env` continues to carry demo
  values; once an operator re-adds a key, the validator refuses to boot.

### Authentication â€” Critical + High

- **HIGH-002** (`core/error_handlers.py`): Duplicate `SecurityValidationError` removed;
  canonical import path is `core.security`. A re-export alias is preserved for
  backwards compatibility.
- **HIGH-005** (`server.py`): Windows PostgreSQL auto-start logic removed; `lifespan`
  now fails fast with an actionable error if `Base.metadata.create_all` cannot reach
  the database.
- **HIGH-013** (`server.py`): JWT delivered via `Set-Cookie` with `HttpOnly` and
  `SameSite=strict`; new `/auth/logout` clears the cookie. Legacy `localStorage`
  support preserved as a phased-rollout mitigation (response still carries
  `access_token`).
- **HIGH-014** (`server.py`): Fixed-window 5/min/IP rate limiter on `/auth/login`
  and `/auth/register` (HTTP 429 above threshold).
- **HIGH-015** (`orchestrator/conversation.py`, `server.py`): `ConversationSession`
  carries `owner_email`; `ConversationDirector.verify_access(...)` validates
  ownership; server endpoints enforce ownership and return HTTP 403 on mismatch.
- **MED-019** (`server.py`): CSRF middleware rejects cross-origin POST/PUT/DELETE/PATCH.
- **MED-021** (`server.py`): Auth input validation â€” email normalisation + RFC-aligned
  format check + password length >= 8 + entropy >= 3 unique characters.
- **MED-022** (`docs/deployment.md`): TLS/HTTPS documented as required for production.
- **MED-023** (`core/models.py`): User model gained `role` column (default `"user"`)
  for RBAC rollout.
- **MED-027** (`core/config.py`): Database URL no longer carries the public
  `postgres@` superuser form in code; the `.env` operator contract is updated.

### Pipeline â€” Critical + High

- **CRIT-001** (`orchestrator/pipelines.py`): Legacy inline pipeline path now
  raises `RuntimeError` unless `aetheris_LEGACY_PIPELINE_ENABLED=true` is set
  (Phase 1 mitigation per manifest Â§3 â€” staged rollout). Default code path is
  `_run_with_decision_engine`.
- **HIGH-011** (`orchestrator/decisions.py`): New `safe_create_task_broadcast(coro,
  name=...)` helper attaches `add_done_callback` that logs the exception chain. All
  four DecisionEngine broadcast sites now use it.
- **HIGH-019** (`orchestrator/pipelines.py`): Claim extraction disabled by default
  via `aetheris_DISABLE_CLAIM_EXTRACTION=1` because `validate_claim` returns
  UNVERIFIED uniformly. Opt-in knob for future re-enable.

### Runtime â€” High

- **HIGH-009** (`core/runtime.py`, `orchestrator/decisions.py`, `orchestrator/aetheris_orchestrator.py`):
  RuntimeEngine is now wired into DecisionEngine; `_dispatch_provider_call` routes
  every provider call through `RuntimeEngine.execute_with_contracts` when the
  engine is configured. Contract enforcement (security, streaming, telemetry) is now
  the default execution path.
- **HIGH-010** (`orchestrator/streaming.py`): `StreamEvent.timestamp` is timezone-aware
  UTC. `__post_init__` coerces naive values to UTC. The `to_dict()` payload now
  carries an explicit offset.
- **HIGH-018** (`agents/prompt_manager.py`): `load_runtime_contracts` is memoised via
  `functools.lru_cache(maxsize=4)`; `clear_prompt_cache()` is exposed for tests
  and SIGHUP reload. Measured: 49/50 calls resolve from cache.

### Providers â€” High

- **HIGH-004** (`api_gateway/rate_limiter.py`): `pool._get_state(...)` (private)
  replaced with `pool.get_provider_state(...)` (public) in the failure handling
  loop of `execute_with_fallback`.
- **HIGH-012** (`api_gateway/rate_limiter.py`): Buggy pre-acquire
  `self.global_semaphore.release()` removed. `ResourceManager._held_permits` counter
  defends against un-paired `release()` calls.

### Database â€” Critical + High

- **CRIT-006** (`alembic.ini`, `migrations/env.py`, `migrations/versions/001_initial_schema.py`):
  Alembic bootstrapped with `Base.metadata` integration. Initial migration creates
  the entire schema (`users`, `conversation_sessions`, `conversation_messages`,
  `checkpoints`, `telemetry_events`) with indexes + FK + JSON columns.
- **HIGH-016** (`core/database.py`, `core/config.py`, `core/models.py`): Engine SSL
  reads `settings.DATABASE_SSL`; `pool_recycle=3600` added so long-idle
  connections are recycled before NAT/firewall kills.
- **HIGH-017** (`core/models.py`): New models `ConversationSessionRecord`,
  `ConversationMessageRecord`, `CheckpointRecord`, `TelemetryEvent` live on
  `Base.metadata`. `User` gained `role` and `updated_at`. JSON columns available
  for checkpoint payloads and telemetry events.
- **MED-025** (`core/database.py`): `pool_recycle=3600` enabled.

### Developer Experience â€” Critical

- **CRIT-002** (`pytest.ini`, `tests/`): Pytest infrastructure installed.
  `tests/` directory contains 14 test files / 102 tests covering passport,
  security, conversation, state machine, validators, pipeline, runtime, providers,
  authentication, database. `asyncio_mode=auto`. Coverage baseline established
  for the Phase 1 subsystems.

### Dependency Updates

- Added: `pytest>=8.0.0`, `pytest-asyncio>=0.24.0`, `pytest-cov>=5.0.0`,
  `ruff>=0.10.0`, `alembic>=1.12.0`.

### Files Changed (Phase 1)

```
alembic.ini                               [NEW]
.env.example                             [NEW REFERENCE â€” operator contract]
migrations/env.py                        [NEW]
migrations/script.py.mako                [NEW]
migrations/versions/001_initial_schema.py [NEW]
pytest.ini                               [NEW]
.pytest_cache/                           [NEW â€” auto-excluded from git]
tests/conftest.py                        [NEW]
tests/test_passport.py                   [NEW]
tests/test_security.py                   [NEW]
tests/test_conversation.py               [NEW]
tests/test_state_machine.py              [NEW]
tests/test_validators.py                 [NEW]
tests/test_pipeline.py                   [NEW]
tests/test_pipeline_repair.py            [NEW]
tests/test_runtime_repair.py             [NEW]
tests/test_providers_repair.py           [NEW]
tests/test_auth_repair.py                [NEW]
tests/test_database_repair.py            [NEW]
.ruff.toml                               [NEW]
orchestrator/pipelines.py                [MOD]
orchestrator/decisions.py                [MOD]
orchestrator/streaming.py                [MOD]
orchestrator/conversation.py             [MOD]
orchestrator/aetheris_orchestrator.py    [MOD]
agents/prompt_manager.py                 [MOD]
api_gateway/rate_limiter.py              [MOD]
core/config.py                           [MOD]
core/database.py                         [MOD]
core/models.py                           [MOD]
core/error_handlers.py                   [MOD]
server.py                                [MOD]
docs/audit/AUDIT_INDEX.md                 [MOD â€” status updates]
docs/repair/REPAIR_LEDGER.md             [MOD â€” REP entries appended]
docs/repair/REPAIR_STATUS.md             [MOD â€” health scores refreshed]
docs/repair/subsystems/PIPELINE.md       [NEW]
docs/repair/subsystems/RUNTIME.md        [NEW]
docs/repair/subsystems/PROVIDERS.md      [NEW]
docs/repair/subsystems/AUTH.md           [NEW]
docs/repair/subsystems/DATABASE.md        [NEW]
docs/repair/checkpoints/PIPELINE_CHECKPOINT.md   [NEW]
docs/repair/checkpoints/RUNTIME_CHECKPOINT.md    [NEW]
docs/repair/checkpoints/PROVIDERS_CHECKPOINT.md  [NEW]
docs/repair/checkpoints/AUTH_CHECKPOINT.md       [NEW]
docs/repair/checkpoints/DATABASE_CHECKPOINT.md    [NEW]
docs/repair/PHASE1_COMPLETION_REPORT.md   [NEW]
```

### Validation

| Gate | Result |
|------|--------|
| Compilation | âœ… Pass |
| Ruff static analysis | âœ… Pass on Phase 1 files (pre-existing E501 / B904 not regressions) |
| Pytest | âœ… 102 / 102 passing |
| Regression | âœ… No existing tests regressed |

### Migration Notes

- Operators MUST rotate `AETHERIS_JWT_SECRET_KEY` before first deploy â€” old secrets
  are rejected.
- Operators MUST replace any live provider key in `.env` with an empty placeholder
  until the secret manager integration ships.
- `aetheris_CORS_ORIGINS` (defaults to localhost ports) MUST be set to production
  origins before launch.
- The `aetheris_LEGACY_PIPELINE_ENABLED=true` flag should NOT be set in production â€”
  it exists solely for staged rollouts comparing both code paths.

# Changelog â€” Phase 1 Releases

> Append-only history of post-audit Phase 1 changes, 2026-06-27.

---

## [0.2.0] â€” 2026-06-27 â€” Phase 1 â€” Core Stabilization âœ…

### Security â€” Emergency (P0)

- **CRIT-004** (`core/config.py`, `server.py`): CORS wildcard with credentials replaced
  by explicit `CORS_ORIGINS` allowlist. `_resolve_cors_origins()` rejects `*` and
  missing origins. Authentication middleware parses `Origin` / `Referer` headers and
  rejects POST/PUT/DELETE/PATCH whose origin is not in the allowlist (CSRF).
- **CRIT-005** (`core/config.py`): Hardcoded default JWT secret removed. `aetherisConfig`
  enforces: rejection of empty, the canonical demo fallback, and any secret under
  32 characters. Operators MUST rotate existing secret before first deploy.
- **CRIT-007** (`core/config.py`): pydantic `field_validator` rejects any provider
  key matching live prefixes (`sk-or-v1-`, `nvapi-`, `gsk_p`, `github_pat_`,
  `sk-proj-`, `sk-ZO`, `AQ.Ab8`). The committed `.env` continues to carry demo
  values; once an operator re-adds a key, the validator refuses to boot.

### Authentication â€” Critical + High

- **HIGH-002** (`core/error_handlers.py`): Duplicate `SecurityValidationError` removed;
  canonical import path is `core.security`. A re-export alias is preserved for
  backwards compatibility.
- **HIGH-005** (`server.py`): Windows PostgreSQL auto-start logic removed; `lifespan`
  now fails fast with an actionable error if `Base.metadata.create_all` cannot reach
  the database.
- **HIGH-013** (`server.py`): JWT delivered via `Set-Cookie` with `HttpOnly` and
  `SameSite=strict`; new `/auth/logout` clears the cookie. Legacy `localStorage`
  support preserved as a phased-rollout mitigation (response still carries
  `access_token`).
- **HIGH-014** (`server.py`): Fixed-window 5/min/IP rate limiter on `/auth/login`
  and `/auth/register` (HTTP 429 above threshold).
- **HIGH-015** (`orchestrator/conversation.py`, `server.py`): `ConversationSession`
  carries `owner_email`; `ConversationDirector.verify_access(...)` validates
  ownership; server endpoints enforce ownership and return HTTP 403 on mismatch.
- **MED-019** (`server.py`): CSRF middleware rejects cross-origin POST/PUT/DELETE/PATCH.
- **MED-021** (`server.py`): Auth input validation â€” email normalisation + RFC-aligned
  format check + password length >= 8 + entropy >= 3 unique characters.
- **MED-022** (`docs/deployment.md`): TLS/HTTPS documented as required for production.
- **MED-023** (`core/models.py`): User model gained `role` column (default `"user"`)
  for RBAC rollout.
- **MED-027** (`core/config.py`): Database URL no longer carries the public
  `postgres@` superuser form in code; the `.env` operator contract is updated.

### Pipeline â€” Critical + High

- **CRIT-001** (`orchestrator/pipelines.py`): Legacy inline pipeline path now
  raises `RuntimeError` unless `aetheris_LEGACY_PIPELINE_ENABLED=true` is set
  (Phase 1 mitigation per manifest Â§3 â€” staged rollout). Default code path is
  `_run_with_decision_engine`.
- **HIGH-011** (`orchestrator/decisions.py`): New `safe_create_task_broadcast(coro,
  name=...)` helper attaches `add_done_callback` that logs the exception chain. All
  four DecisionEngine broadcast sites now use it.
- **HIGH-019** (`orchestrator/pipelines.py`): Claim extraction disabled by default
  via `aetheris_DISABLE_CLAIM_EXTRACTION=1` because `validate_claim` returns
  UNVERIFIED uniformly. Opt-in knob for future re-enable.

### Runtime â€” High

- **HIGH-009** (`core/runtime.py`, `orchestrator/decisions.py`, `orchestrator/aetheris_orchestrator.py`):
  RuntimeEngine is now wired into DecisionEngine; `_dispatch_provider_call` routes
  every provider call through `RuntimeEngine.execute_with_contracts` when the
  engine is configured. Contract enforcement (security, streaming, telemetry) is now
  the default execution path.
- **HIGH-010** (`orchestrator/streaming.py`): `StreamEvent.timestamp` is timezone-aware
  UTC. `__post_init__` coerces naive values to UTC. The `to_dict()` payload now
  carries an explicit offset.
- **HIGH-018** (`agents/prompt_manager.py`): `load_runtime_contracts` is memoised via
  `functools.lru_cache(maxsize=4)`; `clear_prompt_cache()` is exposed for tests
  and SIGHUP reload. Measured: 49/50 calls resolve from cache.

### Providers â€” High

- **HIGH-004** (`api_gateway/rate_limiter.py`): `pool._get_state(...)` (private)
  replaced with `pool.get_provider_state(...)` (public) in the failure handling
  loop of `execute_with_fallback`.
- **HIGH-012** (`api_gateway/rate_limiter.py`): Buggy pre-acquire
  `self.global_semaphore.release()` removed. `ResourceManager._held_permits` counter
  defends against un-paired `release()` calls.

### Database â€” Critical + High

- **CRIT-006** (`alembic.ini`, `migrations/env.py`, `migrations/versions/001_initial_schema.py`):
  Alembic bootstrapped with `Base.metadata` integration. Initial migration creates
  the entire schema (`users`, `conversation_sessions`, `conversation_messages`,
  `checkpoints`, `telemetry_events`) with indexes + FK + JSON columns.
- **HIGH-016** (`core/database.py`, `core/config.py`, `core/models.py`): Engine SSL
  reads `settings.DATABASE_SSL`; `pool_recycle=3600` added so long-idle
  connections are recycled before NAT/firewall kills.
- **HIGH-017** (`core/models.py`): New models `ConversationSessionRecord`,
  `ConversationMessageRecord`, `CheckpointRecord`, `TelemetryEvent` live on
  `Base.metadata`. `User` gained `role` and `updated_at`. JSON columns available
  for checkpoint payloads and telemetry events.
- **MED-025** (`core/database.py`): `pool_recycle=3600` enabled.

### Developer Experience â€” Critical

- **CRIT-002** (`pytest.ini`, `tests/`): Pytest infrastructure installed.
  `tests/` directory contains 14 test files / 102 tests covering passport,
  security, conversation, state machine, validators, pipeline, runtime, providers,
  authentication, database. `asyncio_mode=auto`. Coverage baseline established
  for the Phase 1 subsystems.

### Dependency Updates

- Added: `pytest>=8.0.0`, `pytest-asyncio>=0.24.0`, `pytest-cov>=5.0.0`,
  `ruff>=0.10.0`, `alembic>=1.12.0`.

### Files Changed (Phase 1)

```
alembic.ini                               [NEW]
.env.example                             [NEW REFERENCE â€” operator contract]
migrations/env.py                        [NEW]
migrations/script.py.mako                [NEW]
migrations/versions/001_initial_schema.py [NEW]
pytest.ini                               [NEW]
.pytest_cache/                           [NEW â€” auto-excluded from git]
tests/conftest.py                        [NEW]
tests/test_passport.py                   [NEW]
tests/test_security.py                   [NEW]
tests/test_conversation.py               [NEW]
tests/test_state_machine.py              [NEW]
tests/test_validators.py                 [NEW]
tests/test_pipeline.py                   [NEW]
tests/test_pipeline_repair.py            [NEW]
tests/test_runtime_repair.py             [NEW]
tests/test_providers_repair.py           [NEW]
tests/test_auth_repair.py                [NEW]
tests/test_database_repair.py            [NEW]
.ruff.toml                               [NEW]
orchestrator/pipelines.py                [MOD]
orchestrator/decisions.py                [MOD]
orchestrator/streaming.py                [MOD]
orchestrator/conversation.py             [MOD]
orchestrator/aetheris_orchestrator.py    [MOD]
agents/prompt_manager.py                 [MOD]
api_gateway/rate_limiter.py              [MOD]
core/config.py                           [MOD]
core/database.py                         [MOD]
core/models.py                           [MOD]
core/error_handlers.py                   [MOD]
server.py                                [MOD]
docs/audit/AUDIT_INDEX.md                 [MOD â€” status updates]
docs/repair/REPAIR_LEDGER.md             [MOD â€” REP entries appended]
docs/repair/REPAIR_STATUS.md             [MOD â€” health scores refreshed]
docs/repair/subsystems/PIPELINE.md       [NEW]
docs/repair/subsystems/RUNTIME.md        [NEW]
docs/repair/subsystems/PROVIDERS.md      [NEW]
docs/repair/subsystems/AUTH.md           [NEW]
docs/repair/subsystems/DATABASE.md        [NEW]
docs/repair/checkpoints/PIPELINE_CHECKPOINT.md   [NEW]
docs/repair/checkpoints/RUNTIME_CHECKPOINT.md    [NEW]
docs/repair/checkpoints/PROVIDERS_CHECKPOINT.md  [NEW]
docs/repair/checkpoints/AUTH_CHECKPOINT.md       [NEW]
docs/repair/checkpoints/DATABASE_CHECKPOINT.md    [NEW]
docs/repair/PHASE1_COMPLETION_REPORT.md   [NEW]
```

### Validation

| Gate | Result |
|------|--------|
| Compilation | âœ… Pass |
| Ruff static analysis | âœ… Pass on Phase 1 files (pre-existing E501 / B904 not regressions) |
| Pytest | âœ… 102 / 102 passing |
| Regression | âœ… No existing tests regressed |

### Migration Notes

- Operators MUST rotate `AETHERIS_JWT_SECRET_KEY` before first deploy â€” old secrets
  are rejected.
- Operators MUST replace any live provider key in `.env` with an empty placeholder
  until the secret manager integration ships.
- `aetheris_CORS_ORIGINS` (defaults to localhost ports) MUST be set to production
  origins before launch.
- The `aetheris_LEGACY_PIPELINE_ENABLED=true` flag should NOT be set in production â€”
  it exists solely for staged rollouts comparing both code paths.

