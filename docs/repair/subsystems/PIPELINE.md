# Pipeline Subsystem Report

| Field | Value |
|-------|-------|
| **Subsystem ID** | S1 — Pipeline |
| **Pipeline File** | `orchestrator/pipelines.py` |
| **Health Score (Pre-Phase 1)** | 55/100 |
| **Health Score (Post-Phase 1)** | 80/100 |
| **Δ Health** | +25 |
| **Status** | 🟢 Healthy |
| **Report Date** | 2026-06-27 |

---

## 1. Repairs

### 1.1 CRIT-001 — Dual Execution Paths

| Field | Value |
|-------|-------|
| **Status** | ✅ Verified |
| **Repair ID** | REP-000101 |
| **Files** | `orchestrator/pipelines.py`, `orchestrator/decisions.py` |

The legacy inline pipeline path and the new `_run_with_decision_engine` path coexisted in `run_micro_mode()`. The legacy path ran an inline Breaker → parallel Logician/Creative → Judge synthesis loop in the function body, while the DecisionEngine path executed the same logic via the `DecisionEngine` class. The two paths diverged in error handling and conversation-state management.

**Repair**:

- The legacy branch is now gated behind the environment flag `aetheris_LEGACY_PIPELINE_ENABLED` (default off).
- When the flag is absent, `run_micro_mode(...)` raises `RuntimeError(_legacy_pipeline_blocked_msg())` immediately.
- When the flag is set, a `WARNING` is logged on every invocation so operators notice the legacy code path during A/B staging.

**Validation**: `tests/test_pipeline_repair.py::TestCRIT001LegacyPathBlocked::test_legacy_blocked_without_decision_engine` raises `RuntimeError` containing `CRIT-001`; `test_legacy_path_remains_behind_opt_in_flag` asserts the flag read.

### 1.2 HIGH-019 — Claim Extraction No-Op

| Field | Value |
|-------|-------|
| **Status** | ✅ Verified |
| **Repair ID** | REP-000101 |
| **Files** | `orchestrator/pipelines.py` |

`validate_claim` always returns `UNVERIFIED` with `confidence=0.3`. The full extraction – validation – provenance-tracing loop ran on every request at 50-200ms cost without producing any signal.

**Repair**:

- New helper `_is_claim_extraction_enabled()` reads the `aetheris_DISABLE_CLAIM_EXTRACTION` env var (default `1`). When the var is unset (default), the entire extraction block is skipped.
- Operators can opt back in by setting `aetheris_DISABLE_CLAIM_EXTRACTION=0` once a real `Claim.validate` implementation ships.

**Validation**: tests verify default-disabled, opt-in enabled, and off-token enabled.

### 1.3 HIGH-011 — Fire-and-Forget Tasks

| Field | Value |
|-------|-------|
| **Status** | ✅ Verified |
| **Repair ID** | REP-000101 |
| **Files** | `orchestrator/decisions.py` |

Four `asyncio.create_task(...)` calls in `DecisionEngine` broadcast SSE events fired-and-forgot, swallowing exceptions.

**Repair**:

- New `safe_create_task_broadcast(coro, *, name=...)` helper wraps each broadcast with `add_done_callback(_log_task_exception(name))` that logs the failure chain.
- All 4 broadcast sites (`breaker-failed`, `breaker-passed`, `generation-completed`, `judge-synthesized`) now use the helper.

**Validation**: tests verify exceptions surface in callbacks; success path returns unchanged result.

---

## 2. Files Touched

| File | Status |
|------|--------|
| `orchestrator/pipelines.py` | Modified |
| `orchestrator/decisions.py` | Modified (HIGH-011 + HIGH-009 wiring helpers share `safe_create_task_broadcast`) |
| `tests/test_pipeline_repair.py` | Created |
| `tests/test_pipeline.py` | Modified (smoke test for new helpers) |

---

## 3. Validation

| Gate | Status |
|------|--------|
| Compilation | ✅ Pass |
| Ruff | ✅ No new issues |
| Unit tests | 23/23 (Pipeline + Pipeline-repair + State Machine + Conversation baseline) |
| Regression | ✅ No existing tests failed |

---

## 4. Remaining Risks

| Risk | Severity | Notes |
|------|----------|-------|
| Operators enable legacy path in production | 🟡 Medium | Logged at WARNING on each call; documented in deployment.md |
| Claim extraction re-enabled while still no-op | 🟡 Medium | Manifest ties HIGH-019 mitigation to MED-006 in Phase 3 |
| `_build_frontend_payload` is still private (MED-001) | 🟢 Low | Phase 3 cleanup |

---

## 5. Recommendations

- Phase 2 should fully delete the legacy `run_micro_mode` inline path (after one sprint of A/B per manifest mitigation).
- Phase 2 should add scenario coverage that drives `_run_with_decision_engine` with a mock `streaming_manager` that raises on `emit_event`, validating that `safe_create_task_broadcast` calls actually catch the failure.
- Phase 3 should re-implement the `Claim.validate` pipeline in a way that produces a non-zero `confidence` and connect it to `claim_manager.validate_claim(...)`.

---

## 6. Audit Index Status

| Issue ID | Old Status | New Status |
|----------|------------|------------|
| CRIT-001 | 🔴 Open | ✅ Verified |
| HIGH-011 | 🔴 Open | ✅ Verified |
| HIGH-019 | 🔴 Open | ✅ Verified |
| MED-015 | (Phase 3) | Still open — query history recording (no-op not affected) |
| MED-016 | (Phase 3) | Still open — `transition_conversation_to_failed` helper adoption |
| LOW-018 | (Phase 4) | Still open — structured logging extras |
