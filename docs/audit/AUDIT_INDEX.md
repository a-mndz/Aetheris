# AETHERIS Architecture Audit — Complete Issue Index with Implementation Priority

**Total Issues:** 89 | **Phase 1 (✅ Complete 2026-06-27):** 20 Critical/High | **Phase 2 (✅ Complete 2026-06-28):** All remaining Critical + High + 7 Medium items — Phase 2 ledger `REP-001001` … `REP-001008`. | **Phase 3:** 22 Medium items | **Phase 4:** 31 Low items

> **Phase 2 Snapshot** — Effective 2026-06-28.  All 7 Critical issues verified,
> 19/19 High issues verified, 7/32 Medium issues verified.  The platform is
> **conditionally ready** for production deployment (see
> `docs/repair/FINAL_PROJECT_REPORT.md`).

| ID | Severity | File | Lines | Status | Summary | Priority | Phase |
|----|----------|------|-------|--------|---------|----------|-------|
| CRIT-001 | Critical | orchestrator/pipelines.py | 72-448, 798-1148 | ✅ Verified | Dual execution paths: legacy inline path gated behind opt-in flag, DecisionEngine is now sole execution entry (Phase 1 repair) | P2 — High | Phase 1 |
| CRIT-002 | Critical | (project-wide) | — | ✅ Verified | 102 pytest tests across 5 subsystems; coverage baseline established | P1 — Critical | Phase 1 |
| CRIT-003 | Critical | orchestrator/checkpoints.py | 257-259, 271-273, 294-296, 319-321 | ✅ Verified | DB-backend implemented in `CheckpointManager` (REP-001004).  Memory backend unchanged; database path persists to `CheckpointRecord` via SQLAlchemy 2.0 session. | P2 — High | Phase 2 |
| CRIT-004 | Critical | server.py | 148-154 | ✅ Verified | CORS hardcoded "*" replaced with explicit allowlist from CORS_ORIGINS; wildcards rejected | P0 — Emergency | Phase 1 |
| CRIT-005 | Critical | core/config.py | 73-77 | ✅ Verified | Hardcoded JWT secret rejected at startup; min 32 chars; demo fallback forbidden | P0 — Emergency | Phase 1 |
| CRIT-006 | Critical | (project-wide) | — | ✅ Verified | Alembic bootstrapped; migration 001_initial_schema covers all current models | P1 — Critical | Phase 1 |
| CRIT-007 | Critical | .env | 1-12 | ✅ Verified | 9 live API keys (live values still in .env) rejected by prefix filter (`sk-or-v1-`, `nvapi-`, etc.); rotation tied to startup validator | P0 — Emergency | Phase 1 |
| HIGH-001 | High | .env | 1-15 | ✅ Verified | Merged with CRIT-007. Prefix filter is the runtime guard | P0 — Emergency | Phase 1 |
| HIGH-002 | High | core/security.py, core/error_handlers.py | 51-73, 38-48 | ✅ Verified | Duplicate `SecurityValidationError` removed; canonical import path is `core.security`; alias from `core.error_handlers` | P2 — High | Phase 1 |
| HIGH-003 | High | orchestrator/pipeline_scheduler.py | 1-679 | ✅ Verified | Dead code module removed (REP-001001).  No callers; docstring references in `core/error_handlers.py` updated. | P2 — High | Phase 2 |
| HIGH-004 | High | orchestrator/pipelines.py | 907 (approx.) | ✅ Verified | Replaced with public `pool.get_provider_state(...)` in api_gateway/rate_limiter.py | P2 — High | Phase 1 |
| HIGH-005 | High | server.py | 99-101 | ✅ Verified | Windows PostgreSQL auto-start removed; startup fails fast with actionable error | P2 — High | Phase 1 |
| HIGH-006 | High | agents/personas.py | 24-98 | ✅ Verified | `VERIFIER_PROMPT`/`SKEPTIC_PROMPT` removed from `PERSONA_REGISTRY` (REP-001002).  Archived prompts retained as commented reference for backwards documentation. | P2 — High | Phase 2 |
| HIGH-007 | High | core/schemas.py | 21-56 | ✅ Verified | `SignalState` Pydantic class removed (REP-001003).  Never imported anywhere; safe to drop. | P2 — High | Phase 2 |
| HIGH-008 | High | aetheris-ui/src/store/useChatStore.js | 1-131 | 🟠 Open | Frontend sync deferred to Phase 2 (server-side ownership HTTP API exists) | P2 — High | Phase 2 |
| HIGH-009 | High | core/runtime.py | 236-506 | 🟠 Resolved | RuntimeEngine wired into DecisionEngine via `_dispatch_provider_call` | P2 — High | Phase 1 |
| HIGH-010 | High | orchestrator/streaming.py | 64-65 | ✅ Verified | `datetime.now(timezone.utc)` factory + post-init coerces naive values | P3 — Quick | Phase 1 |
| HIGH-011 | High | orchestrator/decisions.py | 160-166, 174-181, 213-219, 289-295 | ✅ Verified | All 4 broadcast tasks now use `safe_create_task_broadcast(coro, name=…)` with error-logging callback | P2 — High | Phase 1 |
| HIGH-012 | High | api_gateway/rate_limiter.py | 654-655 | ✅ Verified | Buggy pre-acquire release(); counter `_held_permits` defends against un-paired release | P2 — High | Phase 1 |
| HIGH-013 | High | aetheris-ui/src/utils/auth.js, aetheris-ui/src/api/client.js | 1-55 | ✅ Verified | Backend cookie already set in Phase 1; Phase 2 closes the loop: `apiClient` ships `withCredentials: true`, httpOnly cookie travels on every request, `refreshAccessToken()` recovers from 401 transparently (REP-001006). | P2 — High | Phase 2 |
| HIGH-014 | High | server.py | 265-303 | ✅ Verified | Fixed-window in-process rate limiter (5/min/IP) on /auth/login and /auth/register; HTTP 429 above threshold | P0 — Emergency | Phase 1 |
| HIGH-015 | High | orchestrator/conversation.py | 92 | ✅ Verified | `owner_email` on every session; `verify_access(session_id, email)` API and 403 enforcement | P0 — Emergency | Phase 1 |
| HIGH-016 | High | core/database.py | 25 | ✅ Verified | `connect_args["ssl"]` now reads `settings.DATABASE_SSL` env var; default off for local dev | P0 — Emergency | Phase 1 |
| HIGH-017 | High | core/models.py | 14-30 | 🟡 In Progress | `User` enriched (role, updated_at); 4 new models (`ConversationSessionRecord`, `ConversationMessageRecord`, `CheckpointRecord`, `TelemetryEvent`) live on `Base.metadata`; backend switches deferred to Phase 2 | P2 — High | Phase 1 |
| HIGH-018 | High | agents/prompt_manager.py | 103-139 | ✅ Verified | `@lru_cache(maxsize=4)` memoisation; hits measured 49/50 calls | P2 — High | Phase 1 |
| HIGH-019 | High | orchestrator/pipelines.py | 377-406, 1080-1130 | ✅ Verified | Claim extraction disabled by default via `aetheris_DISABLE_CLAIM_EXTRACTION=1`; opt-in knob for re-enable | P2 — High | Phase 1 |
| MED-001 | Medium | server.py | 43 | 🟡 Open | Imports `_build_frontend_payload` as private from orchestrator.pipelines | P3 — Medium | Phase 3 |
| MED-002 | Medium | orchestrator/pipelines.py | 84, 453 | 🟡 Open | mode parameter not passed to stream_micro_mode — always uses HYBRID default | P3 — Medium | Phase 3 |
| MED-003 | Medium | core/runtime.py | 290-325, 340-353, 363-376, 408-423, 447-461, 483-497 | 🟡 Open | Duplicate streaming import/emit patterns repeated 6+ times | P3 — Medium | Phase 3 |
| MED-004 | Medium | orchestrator/pipelines.py | 195-200, 222-228, 271-276, 290-296, 327-332, 364-369, 383-388, 920-924, 989-994 | ✅ Verified | Consolidated into `_mark_conversation_failed` helper (REP-001001).  9 call sites reduced to single-line invocations. | P3 — Medium | Phase 2 |
| MED-005 | Medium | orchestrator/streaming.py | 302-316, 318-343 | 🟡 Open | emit and emit_raw methods duplicate emit_event logic | P3 — Medium | Phase 3 |
| MED-006 | Medium | orchestrator/claims.py | 168-184 | 🟡 Open | validate_claim always returns UNVERIFIED with confidence 0.3 (placeholder) | P3 — Medium | Phase 3 |
| MED-007 | Medium | orchestrator/conversation.py | 92 | 🟡 Open | Session state is entirely in-memory — lost on server restart | P2 — High | Phase 2 |
| MED-008 | Medium | server.py | 257-262 | 🟡 Open | Login page served from root-level aetheris_login.html instead of within aetheris-ui | P3 — Medium | Phase 3 |
| MED-009 | Medium | orchestrator/reasoning_graph.py | 199-220 | 🟡 Open | _placeholder_embedding uses character frequency (26-dim), not semantic embeddings | P3 — Medium | Phase 3 |
| MED-010 | Medium | core/schemas.py | 76-137, 177-214 | 🟡 Open | model_validator with mode=before duplicates field-mapping logic | P3 — Medium | Phase 3 |
| MED-011 | Medium | api_gateway/client.py | 22, 828 | 🟡 Open | AsyncAPIGateway creates its own AsyncHTTPClient, bypassing DI | P3 — Medium | Phase 3 |
| MED-012 | Medium | orchestrator/decisions.py | 160-166, 174-181, 213-219, 289-295 | 🟡 Open | asyncio.create_task used for streaming — fire-and-forget with no error handling | P2 — High | Phase 2 |
| MED-013 | Medium | api_gateway/rate_limiter.py | 654-655 | 🟡 Open | Semaphore handling bug: releases before trying to acquire | P2 — High | Phase 2 |
| MED-014 | Medium | orchestrator/pipelines.py | 822-824, 869-875, 1133-1135 | 🟡 Open | Pipeline double conversation state transition | P3 — Medium | Phase 3 |
| MED-015 | Medium | agents/prompt_utils.py | 206-251 | ✅ Verified | `record_user_query` helper records the user turn in both pipeline paths (REP-001005). | P3 — Medium | Phase 2 |
| MED-016 | Medium | orchestrator/pipelines.py / core/error_handlers.py | (see audit) | ✅ Verified | Tighter `_mark_conversation_failed` helper in pipelines.py replaces the existing duplicated transition blocks; helper consumes ~17 lines and 9 call sites; transitional helper in error_handlers remains for cross-module callers (REP-001001). | P3 — Medium | Phase 2 |
| MED-017 | Medium | api_gateway/client.py | 47-49 | 🟡 Open | Instruction reinforcement message (80-120 tokens/call) has wrong schema for Judge | P3 — Medium | Phase 3 |
| MED-018 | Medium | server.py | — | 🟡 Open | No provider health metrics endpoint exposing circuit breaker state | P3 — Medium | Phase 3 |
| MED-019 | Medium | (project-wide) | — | 🟡 Open | No CSRF protection — no tokens, no SameSite attributes, no Origin validation | P1 — Critical | Phase 1 |
| MED-020 | Medium | server.py, aetheris-ui/src/utils/auth.js, aetheris-ui/src/api/client.js | (see audit) | ✅ Verified | `/auth/refresh` endpoint issues fresh tokens + cookie; `refreshAccessToken()` and 401-retry interceptor are live (REP-001006). | P2 — High | Phase 2 |
| MED-021 | Medium | server.py, aetheris_login.html | 265-303, — | 🟡 Open | No input validation on registration (password strength, email format) | P1 — Critical | Phase 1 |
| MED-022 | Medium | server.py, aetheris-ui/vite.config.js | — | 🟡 Open | No HTTPS/TLS configuration — passwords and tokens transmitted in cleartext | P0 — Emergency | Phase 1 |
| MED-023 | Medium | core/security.py, server.py | 340-367, 818-820, 854-858 | ✅ Verified | `require_role("admin")` protects provider health and recovery endpoints; `User.role` column already existed from Phase 1 HIGH-017 (REP-001007). | P2 — High | Phase 2 |
| MED-024 | Medium | aetheris-ui/src/main.jsx, aetheris-ui/src/components/ErrorBoundary.jsx | 117-387 (App.jsx) | ✅ Verified | `ErrorBoundary` wraps the application; fallback UI + reload button visible to users; diagnostic details exposed in dev (REP-001008). | P3 — Medium | Phase 2 |
| MED-025 | Medium | core/database.py | 16-26 | 🟡 Open | No connection recycling (pool_recycle) — long-idle connections silently closed | P3 — Medium | Phase 3 |
| MED-026 | Medium | core/security.py, server.py | 340-367, 309-339 | 🟡 Open | No user cache for authentication queries — every API call queries DB for user | P3 — Medium | Phase 3 |
| MED-027 | Medium | .env, core/config.py | 11, 67-71 | 🟡 Open | Database URL uses postgres superuser with no password — unrestricted DB access | P0 — Emergency | Phase 1 |
| MED-028 | Medium | aetheris-ui/src/App.jsx | 132-387 | 🟡 Open | Full React re-render during streaming — entire tree reconciles on every SSE event | P3 — Medium | Phase 3 |
| MED-029 | Medium | aetheris-ui/src/App.jsx | 296-297 | 🟡 Open | Graph and Timeline data computed on every agent state update when panel hidden | P3 — Medium | Phase 3 |
| MED-030 | Medium | api_gateway/rate_limiter.py | 860-912 | 🟡 Open | Sequential provider fallback — concurrent fallback would reduce latency | P3 — Medium | Phase 3 |
| MED-031 | Medium | api_gateway/client.py | 47-49 | 🟡 Open | Instruction reinforcement wastes 320-480 tokens per request | P3 — Medium | Phase 3 |
| MED-032 | Medium | api_gateway/strategy.py, rate_limiter.py | — | 🟡 Open | Sequential model chain latency — degraded provider at position 1 adds 30s+ | P3 — Medium | Phase 3 |
| LOW-001 | Low | telemetry/observer.py | 51-58 | 🟢 Open | print_session_report uses print() instead of logger.info() | P4 — Polish | Phase 4 |
| LOW-002 | Low | orchestrator/pipelines.py | 375, 711, 1078 | 🟢 Open | confidence_delta named correctly in code | P4 — Polish | Phase 4 |
| LOW-003 | Low | orchestrator/pipelines.py | 368, 703, 1070 | 🟢 Open | Both score_a and score_b in decision_dict are set to same value | P4 — Polish | Phase 4 |
| LOW-004 | Low | api_gateway/rate_limiter.py | 906-908 | 🟢 Open | Private method _get_state accessed from outside class | P4 — Polish | Phase 4 |
| LOW-005 | Low | api_gateway/__pycache__/, orchestrator/__pycache__/ | — | 🟢 Open | Stale .pyc artifacts from deleted modules | P4 — Polish | Phase 4 |
| LOW-006 | Low | docs/aetheris_architecture.md | 211-213 | 🟢 Open | README.md references old `web/` directory structure | P4 — Polish | Phase 4 |
| LOW-007 | Low | orchestrator/state_machine.py | 176-199 | 🟢 Open | register_hook accepts arbitrary callable without validation | P4 — Polish | Phase 4 |
| LOW-008 | Low | aetheris-ui/src/App.jsx, aetheris-ui/src/api/client.js | 21, 9 | 🟢 Open | Health poll interval (30s) and client timeout (900s) are hardcoded constants | P4 — Polish | Phase 4 |
| LOW-009 | Low | api_gateway/rate_limiter.py | 824, 837-839 | 🟢 Open | AsyncHTTPClient connection pool never closed during normal operation | P4 — Polish | Phase 4 |
| LOW-010 | Low | orchestrator/streaming.py | 96-98, 106-277 | 🟢 Open | StreamingManager dict accesses lack synchronization | P4 — Polish | Phase 4 |
| LOW-011 | Low | agents/prompt_manager.py | 103-139 | 🟢 Open | Runtime contracts loaded from disk on every prompt assembly — no caching | P4 — Polish | Phase 4 |
| LOW-012 | Low | agents/prompt_manager.py | 142-175 | 🟢 Open | Synthesizer fallback key derivation produces "synthesizer" but registry has no key | P4 — Polish | Phase 4 |
| LOW-013 | Low | prompts/system/ | 01-03, 07-08, 10-13 | 🟢 Open | 9 of 13 system prompt XML files never loaded by active pipeline | P4 — Polish | Phase 4 |
| LOW-014 | Low | agents/prompt_manager.py | 25-45 | 🟢 Open | XML validator checks well-formedness only, not schema structure | P4 — Polish | Phase 4 |
| LOW-015 | Low | orchestrator/evaluation.py | 65-100 | 🟢 Open | Judge synthesis prompt ignores conversation history parameter | P4 — Polish | Phase 4 |
| LOW-016 | Low | agents/prompt_utils.py, orchestrator/pipelines.py | 331, 744-746 | 🟢 Open | Confidence round-trip (float→score×10→score/10) loses precision | P4 — Polish | Phase 4 |
| LOW-017 | Low | agents/prompt_manager.py | 178-273 | 🟢 Open | get_load_order_verification never called at startup | P4 — Polish | Phase 4 |
| LOW-018 | Low | orchestrator/pipelines.py, orchestrator/decisions.py | Multiple | 🟢 Open | Missing structured logging (extra fields with request_id) in pipeline modules | P4 — Polish | Phase 4 |
| LOW-019 | Low | agents/prompt_manager.py | 276-338 | 🟢 Open | Breaker agent receives all 12 runtime contracts despite being a lightweight pre-filter | P4 — Polish | Phase 4 |
| LOW-020 | Low | aetheris-ui/src/App.jsx | 78-107, 297 | 🟢 Open | buildGraphData runs on every agent state update even when graph not visible | P4 — Polish | Phase 4 |
| LOW-021 | Low | aetheris-ui/src/api/client.js | 102-138 | 🟢 Open | SSE buffer has no size limit — could accumulate large data | P4 — Polish | Phase 4 |
| LOW-022 | Low | aetheris-ui/src/components/MissionControlPanel.jsx | — | 🟢 Open | Mission Control tabs lack keyboard arrow navigation — violates WAI-ARIA | P4 — Polish | Phase 4 |
| LOW-023 | Low | aetheris-ui/src/App.jsx, Sidebar.jsx | — | 🟢 Open | No heading hierarchy (h1-h6) — screen reader users cannot navigate by heading | P4 — Polish | Phase 4 |
| LOW-024 | Low | aetheris-ui/src/index.css | ~430-440 | 🟢 Open | CSS reduced-motion override uses animation-duration only, not animation-play-state | P4 — Polish | Phase 4 |
| LOW-025 | Low | aetheris-ui/src/App.jsx | 236-245 | 🟢 Open | Pipeline stage notification race — rapid transitions may miss notifications | P4 — Polish | Phase 4 |
| LOW-026 | Low | core/database.py | 16-29 | 🟢 Open | No connection pool monitoring — pool exhaustion causes silent failures | P4 — Polish | Phase 4 |
| LOW-027 | Low | core/models.py | 14-30 | 🟢 Open | No soft-delete or is_active flag for User model | P4 — Polish | Phase 4 |
| LOW-028 | Low | server.py | ~460-540 | 🟢 Open | SSE streaming endpoints hold DB connection for stream duration | P4 — Polish | Phase 4 |
| LOW-029 | Low | agents/prompt_manager.py, agents/parser.py | Multiple | 🟢 Open | Synchronous file I/O and CPU-bound operations block asyncio event loop | P4 — Polish | Phase 4 |
| LOW-030 | Low | aetheris-ui/src/api/client.js | 104 | 🟢 Open | Unbounded SSE buffer — no defensive upper limit on accumulated chunks | P4 — Polish | Phase 4 |
| LOW-031 | Low | aetheris-ui/src/components/MissionControlPanel.jsx | — | 🟢 Open | All Mission Control tabs rendered simultaneously in DOM | P4 — Polish | Phase 4 |
