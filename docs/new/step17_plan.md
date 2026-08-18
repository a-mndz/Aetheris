# Step 17 — Dashboard metrics, namespaced (docs/new/guide.md)

## Context

`docs/new/guide.md` Step 17 (line 681) requires emitting all nine RFC-005 §4
metric namespaces (`execution.*`, `quality.*`, `resources.*`, `prediction.*`,
`learning.*`, `environment.*`, `manifest.*`, `scheduler.*`, `planner.*`).
RFC-005 owns the *spec* (the exact key list); each component module owns
*emission*. One namespace (`prediction.*`, via `PredictionLayer.record_actuals`)
is already fully compliant and is the pattern to replicate for the other eight.

Confirmed decisions:
- **No new feature flag** — `guide.md`'s traceability table shows Step 17's
  flag column as `—`; this is pure additive telemetry (new dict keys/read-only
  properties), no behavior change, safe to land unconditionally.
- **Emit all 9 namespaces now**, using the user's chosen scope: every RFC-005
  §4.1 example key must be present in the output. Fields with no real data
  source yet (`resources.gpu/cpu/memory`, `resources.rate_limit.headroom`,
  `resources.connection_pool.size`, `environment.cuda_version/container`,
  `manifest.graph_version/graph_fingerprint`, `learning.graph.fingerprint`,
  `planner.fingerprint.hash`) are set to `None` with a `ponytail:` comment
  noting they're populated in Step 18 (ResourceManager) / Step 19
  (ExecutionManifest, fingerprinting, HostPrimitives). `environment.os` and
  `environment.python_version` ARE implemented for real (free stdlib
  `platform` calls, no reason to stub them).
- **Flat dict, not nested** — matches the existing `prediction_telemetry`
  precedent and the RFC's own naming convention (namespace is baked into the
  key prefix already).
- **No new module** — aggregation is a staticmethod on `ExecutionManager`,
  same as the existing `_aggregate_rag_telemetry`. Each producing module
  returns its own small dict; no central telemetry bus.

## Changes by file

### `orchestrator/scheduler.py` — owns `execution.node.*` + `scheduler.*`

Add a `_telemetry: dict[str, Any]` instance attr and a `telemetry` property
(same pattern as `ExecutionPlanner.last_skill_plan`). Inside `run()`, track
via simple counters closed over by the existing worker/mark_completed/
mark_failed closures — no signature change to `run()`:
- `queued` — incremented in `_enqueue_unlocked` (already lock-protected)
- `started` — incremented in `worker()` right after `running.add(task_id)`
- `completed` / `failed` — incremented in `mark_completed` / `mark_failed`
- `promoted: set[str]` — add `task_id` in `_sort_ready_unlocked`'s `key()`
  closure when the starvation-promotion branch fires (a set, not a counter,
  since `key()` re-runs every sort)
- `priority_band` histogram — static count from `graph.nodes` by `.priority`

Set `self._telemetry` right before `return results` (and also before the
`raise RuntimeError` in the `if errors:` branch, so a failed run still carries
partial telemetry):

```python
self._telemetry = {
    "execution.node.started": counters["started"],
    "execution.node.completed": counters["completed"],
    "execution.node.failed": counters["failed"],
    "scheduler.node.queued": counters["queued"],
    "scheduler.node.released": counters["started"],
    "scheduler.priority_band": priority_band_histogram,
    "scheduler.starvation_promoted": len(promoted),
}
```

`execution.retries` / `execution.repairs` are NOT scheduler concerns (no retry
mechanism exists) — sourced in `execution_manager.py` from `repair_result`.

### `orchestrator/execution_planner.py` — owns `planner.output.*` / `planner.template.fallback`

`create_graph()` already calls `validate_or_fallback(...)` twice (lines 59,
75) and discards `(used_fallback, errors)` via `_, _`. Capture into instance
state + expose via a new `last_planner_telemetry` property, same pattern as
`last_skill_plan`:

```python
def __init__(self, skill_composer=None):
    ...
    self._last_graph_valid: bool = True
    self._last_fallback_used: bool = False

@property
def last_planner_telemetry(self) -> dict[str, Any]:
    return {
        "planner.output.valid": self._last_graph_valid,
        "planner.output.invalid": not self._last_graph_valid,
        "planner.template.fallback": self._last_fallback_used,
    }
```

Replace `graph, _, _ = validate_or_fallback(...)` with
`graph, used_fallback, _errors = validate_or_fallback(...)` at both call sites
(lines 59 and 75), set `self._last_fallback_used`/`self._last_graph_valid`
right after each.

### `orchestrator/versioning.py` — owns `environment.*` + `manifest.*`

Add two functions next to the existing `architecture_version`/`git_commit`
module-level constants (same "computed once at import" convention):

```python
import platform

def capture_environment_snapshot() -> dict[str, Any]:
    return {
        "environment.os": platform.system() or "unknown",
        "environment.python_version": platform.python_version(),
        "environment.cuda_version": None,  # ponytail: Step 19 HostPrimitives
        "environment.container": None,     # ponytail: Step 19 HostPrimitives
    }

environment_snapshot: dict[str, Any] = capture_environment_snapshot()


def manifest_metrics(*, graph: Any = None) -> dict[str, Any]:
    return {
        "manifest.architecture_version": architecture_version,
        "manifest.graph_version": getattr(graph, "graph_version", None),      # ponytail: Step 19
        "manifest.graph_fingerprint": getattr(graph, "graph_fingerprint", None),  # ponytail: Step 19
        "manifest.git_commit": git_commit,
    }
```

Use `Any` for the `graph` param (no `TaskGraph` import — `versioning.py`
currently has zero orchestrator/core imports; keep it that way).

### `orchestrator/execution_manager.py` — owns `quality.*`, `resources.*`, aggregation

No changes to `budget.py`, `meta_reasoner.py`, `strategic_planner.py` — their
existing return values (`BudgetSnapshot`, `mutation_audit_trail`) are read
directly inline; adding "telemetry methods" there for 1-2 field reads would be
pure ceremony.

Add `from orchestrator import versioning` import.

Add a module-level template constant (all 41 RFC-005 §4.1 keys, default
`None`) plus a merge staticmethod, mirroring `_aggregate_rag_telemetry`:

```python
_DASHBOARD_METRIC_TEMPLATE: dict[str, Any] = { ...all 41 keys: None... }

@staticmethod
def _assemble_dashboard_metrics(*sources: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(ExecutionManager._DASHBOARD_METRIC_TEMPLATE)
    for source in sources:
        if source:
            merged.update(source)
    return merged
```

Wiring inside `execute()`:
- After `graph`/`budget_snapshot`/`strategic_plan` exist (~line 198, before
  the `needs_clarification` check), build the branch-independent dicts:
  `resource_metrics` (from `budget_snapshot` + `scheduler_concurrency_limit`,
  rest `None` with ponytail comments for Step 18/19), `manifest_metrics`
  (`versioning.manifest_metrics(graph=graph)`), `environment_metrics`
  (`versioning.environment_snapshot`), `planner_metrics` (merge
  `self._execution_planner.last_planner_telemetry` with `planner.invocation`
  = `strategic_plan is not None` and `planner.fingerprint.hash` = `None`),
  `quality_metrics_initial` (from `initial_stage_assessment`).
- In the `needs_clarification` branch (~line 219): add
  `"dashboard_metrics": self._assemble_dashboard_metrics(resource_metrics,
  manifest_metrics, environment_metrics, planner_metrics,
  quality_metrics_initial)` — execution/scheduler/prediction stay `None` via
  template since the scheduler never ran.
- In the `success` branch, after `firewall_result`/`consensus_result`/
  `prediction_telemetry`/`repair_result` exist (~line 306, before
  `rag_telemetry = ...`): build `quality_metrics` (refresh
  `unsupported_claim_count` from `firewall_result`, add agreement/
  contradiction from `consensus_result` when present), `learning_metrics`
  (`learning.mutation.audit` from `meta_result.mutation_audit_trail`, rest
  `None`), `execution_metrics` (`**scheduler.telemetry`, plus
  `execution.repairs` from `repair_result.repair_count` when present,
  `execution.retries: None`). Assemble
  `dashboard_metrics = self._assemble_dashboard_metrics(resource_metrics,
  manifest_metrics, environment_metrics, planner_metrics, quality_metrics,
  learning_metrics, execution_metrics, prediction_telemetry)`. Add
  `"dashboard_metrics": dashboard_metrics` to the returned dict next to
  `rag_telemetry`.

This is additive only — `prediction_telemetry`/`rag_telemetry`/
`memory_telemetry` stay untouched and are still returned as-is; their content
is duplicated (by reference to the same source data) into `dashboard_metrics`
per RFC-005's unified-namespace requirement.

## Tests

Follow existing conventions: plain pytest, function-based, no mocks, assert
directly on dict keys.

- **`tests/test_scheduler.py` (new file)** — scheduler has no dedicated test
  file yet. Add: node started/completed/failed counts on a small multi-node
  graph; queued == released for a linear graph; priority-band histogram
  matches a mixed-priority graph. Skip a real starvation-promotion test (would
  need a >60s wait or a monkeypatched clock — not worth it for this step).
- **`tests/test_execution_manager.py`** (existing file, add functions):
  - `last_planner_telemetry` valid-path and fallback-path assertions (or add
    to a new small `tests/test_execution_planner.py` if that file already
    exists — check first).
  - Full `execute()` run asserts every one of the 41 template keys is present
    in `result["dashboard_metrics"]`.
  - `needs_clarification` branch asserts `execution.node.started is None`
    (unrun stage) while `quality.confidence is not None` (already computed).
  - With `prediction` flag on: `dashboard_metrics["prediction.tokens.actual"]
    == prediction_telemetry["prediction.tokens.actual"]`.
- **`tests/test_versioning.py`** (existing file, add 2 functions):
  `capture_environment_snapshot()` returns all 4 keys, os/python_version
  non-empty strings, cuda/container `None`; `manifest_metrics()` returns
  `architecture_version`/`git_commit` matching the module constants, and
  `None` graph fields when `graph=None`.

Run `.venv\Scripts\python.exe -m pytest -q` after — must stay green (currently
260 passed, 2 pre-existing unrelated Windows `tmp_path` errors in
`test_skills.py`).

## Doc/version bookkeeping (per guide.md "definition of done")

- `tools/check_architecture_version.py`'s watchlist includes `scheduler.py`,
  `execution_manager.py`, `execution_planner.py`, `versioning.py` — all four
  change here, so bump `architecture_version` in `orchestrator/versioning.py`:
  `"0.1.2"` → `"0.1.3"`.
- Add `DEC-018` to `docs/new/decision_register.md` (current highest is
  DEC-017): dashboard metrics namespace emitted unconditionally, no new flag,
  9 namespaces merged into `dashboard_metrics` via
  `ExecutionManager._assemble_dashboard_metrics` over an RFC-005 §4.1 key
  template; unsourced fields `None` pending Step 18/19; `architecture_version`
  bumped 0.1.2 → 0.1.3.
- Run the four CI scripts (`check_rfc_index`, `check_adr_index`,
  `check_decision_register`, `check_architecture_version --stdin`) to confirm
  green, matching the baseline-verification convention every prior step used.

## Update guide.md

Once implemented and tests pass, change Step 17's checkbox (`docs/new/guide.md`
lines 681-686) from `☐` to `☑`, mark the sub-bullet `[x]`, append
`*(completed 2026-07-14)*` to the heading, and add an "Exit gate (met)" note
listing the new tests and the full regression pass count — matching the exact
style of every other completed step (15, 16) in the file.
