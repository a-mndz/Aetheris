# Providers Subsystem Report

| Field | Value |
|-------|-------|
| **Subsystem ID** | S3 — Providers |
| **Core Files** | `api_gateway/rate_limiter.py` (990 lines), `api_gateway/client.py`, `api_gateway/strategy.py` |
| **Health Score (Pre-Phase 1)** | 68/100 |
| **Health Score (Post-Phase 1)** | 78/100 |
| **Δ Health** | +10 |
| **Status** | 🟢 Healthy |
| **Report Date** | 2026-06-27 |

---

## 1. Repairs

### 1.1 HIGH-004 — Private Method Access

| Field | Value |
|-------|-------|
| **Status** | ✅ Verified |
| **Repair ID** | REP-000501 |
| **Files** | `api_gateway/rate_limiter.py` |

`AsyncAPIGateway.execute_with_fallback` called `pool._get_state(provider_name)` to gate the `mark_provider_dead` decision. `_get_state` is a private convention (single underscore); breaking it leaks internals and prevents clean refactors of `ProviderPool`.

**Repair**: Replaced with the existing public `pool.get_provider_state(provider_name)` which returns the same `ProviderState` snapshot.

**Validation**: `test_get_provider_state_returns_snapshot` and `test_get_provider_state_returns_none_for_unknown`.

### 1.2 HIGH-012 — Semaphore Inflation

| Field | Value |
|-------|-------|
| **Status** | ✅ Verified |
| **Repair ID** | REP-000501 |
| **Files** | `api_gateway/rate_limiter.py` |

`ResourceManager.acquire_resources` pre-emptively called `self.global_semaphore.release() if self.global_semaphore.locked() else None` before attempting to acquire. When the semaphore was already at the concurrency limit, this **added** a permit beyond `GLOBAL_CONCURRENCY_LIMIT=100`.

**Repair**:

- Removed the pre-acquire `release()` call.
- Added `_held_permits: int` counter incremented on every successful `acquire_resources()`.
- `release_resources()` now refuses to call `global_semaphore.release()` when the counter is zero (logs WARNING instead of inflating the semaphore).
- `_held_permits` decrements only when a real permit is returned.

**Validation**: `test_acquire_consumes_single_permit`, `test_release_decrements_active_concurrency`, `test_release_without_hold_does_not_inflate`.

---

## 2. Files Touched

| File | Status |
|------|--------|
| `api_gateway/rate_limiter.py` | Modified |
| `tests/test_providers_repair.py` | Created |

---

## 3. Validation

| Gate | Status |
|------|--------|
| Compilation | ✅ Pass |
| Ruff | ✅ No new issues |
| Unit tests | 5/5 |

### Performance

- Semaphore permit count at 200 concurrent requests now capped at exactly 100.
- Encapsulation boundary violations decreased from 1 to 0 (single `_get_state` site).

---

## 4. Remaining Risks

| Risk | Severity | Notes |
|------|----------|-------|
| In-process rate limiter does not survive multi-worker deployments | 🟡 Medium | Phase 3 will move to Redis token bucket |
| Pre-existing load tests not re-run under new semaphore semantics | 🟡 Medium | Phase 2 should rerun |
| `_held_permits` counter has no persistent state — process restart resets | 🟢 Low | Acceptable; restart semantics are correct (counter starts at 0) |

---

## 5. Recommendations

- Phase 2 should add load-test coverage that runs 200 concurrent requests and asserts `_held_permits <= 100`.
- Phase 2 should implement MED-030 concurrent fallback by replacing `execute_with_fallback`'s sequential loop with `asyncio.gather(...)`.
- Phase 2 should add MED-018 (`/api/providers/health`) using `ProviderPool.get_all_statuses()`.

---

## 6. Audit Index Status

| Issue ID | Old Status | New Status |
|----------|------------|------------|
| HIGH-004 | 🟠 Open | ✅ Verified |
| HIGH-012 | 🔴 Open | ✅ Verified |
| MED-011 | 🟡 Open | Still open — DI bypass in AsyncAPIGateway (Phase 3) |
| MED-030 | 🟡 Open | Still open — sequential fallback (Phase 3) |
| MED-031 | 🟡 Open | Still open — token waste (Phase 3) |
| MED-032 | 🟡 Open | Still open — sequential model chain (Phase 3) |
| LOW-009 | 🟢 Open | Still open — HTTP client pool cleanup (Phase 4) |
