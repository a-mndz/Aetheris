# AETHERIS Architecture Audit — Full Report

**Audit Date:** 2026-06-27
**Auditor:** Principal Software Architect
**Scope:** Complete static architectural analysis of the AETHERIS (Adaptive Multi-Model Reasoning Orchestrator) repository.

---

## 1. Folder Organization

### Assessment: GOOD

The repository follows a clear modular monolith structure with well-named packages:

| Directory | Purpose | Assessment |
|-----------|---------|------------|
| `core/` | Configuration, schemas, security, database, runtime contracts | ✅ Clean |
| `api_gateway/` | Provider abstraction, rate limiting, model strategy | ✅ Clean |
| `agents/` | Prompt assembly, JSON parsing, personas | ✅ Clean |
| `orchestrator/` | Pipeline execution, state machine, streaming, claims | ⚠️ Overloaded |
| `telemetry/` | Token/cost tracking | ✅ Clean |
| `prompts/` | XML prompt templates (runtime + system) | ✅ Clean |
| `aetheris-ui/` | React/Vite frontend | ✅ Clean |

**Issues:**
- `orchestrator/` contains 14 modules — too many responsibilities for one package. Could be split into `orchestrator/pipeline/`, `orchestrator/state/`, `orchestrator/memory/`.
- `api_gateway/rate_limiter.py` (990 lines) contains ProviderPool, ResourceManager, AsyncAPIGateway, and TokenBucket — at least 4 distinct components in one file.
- `root-level files`: `aetheris_login.html` (538KB), `aetheris_hero_video_graded.mp4` (345KB), `recovered_blobs.txt`, `recovered_rate_limiter.txt` — artifacts that should be in a `static/` or `media/` directory.

---

## 2. Module Boundaries

### Assessment: FAIR

**Strengths:**
- `core/` has no internal imports from `orchestrator/` or `api_gateway/` — proper bottom-layer positioning
- `telemetry/observer.py` has no project imports — clean terminal dependency
- Each package has a clean `__init__.py` that re-exports public API

**Violations:**
| Violation | File | Description |
|-----------|------|-------------|
| Boundary leak | `orchestrator/pipelines.py:44` | Imports `_build_frontend_payload` as private from pipelines.py in server.py |
| Cross-layer coupling | `core/runtime.py:291` | Imports from `orchestrator.streaming` inside method body |
| Cross-layer coupling | `core/error_handlers.py:244` | Imports from `orchestrator.conversation` inside method body |
| Layer skip | `orchestrator/evaluation.py:18` | Imports directly from `agents/` instead of through orchestration layer |

---

## 3. Dependency Graph

```
main.py / server.py
    ├── api_gateway/__init__
    │   ├── api_gateway/client.py
    │   │   ├── core/config.py        (terminal)
    │   │   └── telemetry/observer.py (terminal)
    │   ├── api_gateway/rate_limiter.py
    │   │   ├── api_gateway/client.py
    │   │   ├── api_gateway/strategy.py (terminal)
    │   │   ├── core/security.py
    │   │   │   ├── core/config.py
    │   │   │   ├── core/database.py
    │   │   │   │   └── core/config.py
    │   │   │   └── core/models.py
    │   │   │       └── core/database.py
    │   │   └── core/passport.py
    │   │       └── core/validators.py (terminal)
    │   └── api_gateway/strategy.py
    ├── core/__init__
    │   ├── core/passport.py
    │   └── core/runtime.py
    │       ├── core/passport.py
    │       └── core/schemas.py (terminal)
    ├── orchestrator/__init__
    │   ├── orchestrator/pipelines.py
    │   │   ├── agents/parser.py
    │   │   ├── agents/prompt_utils.py
    │   │   │   └── agents/prompt_manager.py
    │   │   │       └── agents/personas.py (terminal)
    │   │   ├── api_gateway/rate_limiter.py
    │   │   ├── api_gateway/strategy.py
    │   │   ├── core/passport.py
    │   │   ├── core/security.py
    │   │   ├── core/schemas.py
    │   │   ├── orchestrator/evaluation.py
    │   │   │   ├── core/schemas.py
    │   │   │   ├── agents/parser.py
    │   │   │   └── agents/prompt_utils.py
    │   │   └── orchestrator/memory.py (terminal)
    │   ├── orchestrator/decisions.py
    │   │   ├── agents/parser.py
    │   │   ├── agents/prompt_utils.py
    │   │   ├── api_gateway/rate_limiter.py
    │   │   ├── api_gateway/strategy.py
    │   │   ├── core/passport.py
    │   │   ├── core/schemas.py
    │   │   ├── core/error_handlers.py
    │   │   │   └── (circular import risk with orchestrator via core/error_handlers.py:244)
    │   │   ├── orchestrator/evaluation.py
    │   │   ├── orchestrator/memory.py
    │   │   └── orchestrator/streaming.py
    │   ├── orchestrator/claims.py
    │   │   └── orchestrator/reasoning_graph.py (terminal)
    │   ├── orchestrator/conversation.py
    │   │   └── core/validators.py
    │   ├── orchestrator/checkpoints.py
    │   │   ├── core/validators.py
    │   │   └── core/error_handlers.py
    │   ├── orchestrator/memory_manager.py (terminal-ish, tiktoken optional)
    │   ├── orchestrator/state_machine.py (terminal-ish)
    │   └── orchestrator/streaming.py (terminal-ish, asyncio only)
    └── telemetry/observer.py (terminal)
```

**Assessment:** The dependency graph is largely acyclic. No true circular imports exist. However, `core/error_handlers.py:244` imports from `orchestrator.conversation` and `core/runtime.py:291` imports from `orchestrator.streaming` — these create **back-edges from the core layer to the orchestration layer**, violating the intended layer hierarchy.

---

## 4. Architecture Violations

### 4.1 Circular Dependencies

**Verdict: NO CIRCULAR IMPORTS FOUND**

The import graph is a DAG. All import chains terminate in `core/config.py`, `core/validators.py`, `telemetry/observer.py`, or standard library modules.

### 4.2 Dead Code

| File | Lines | Component | Age | Impact |
|------|-------|-----------|-----|--------|
| orchestrator/pipeline_scheduler.py | 1-679 | PipelineScheduler | Post-refactor | Entire module is dead — never imported, never used |
| agents/personas.py VERIFIER_PROMPT | 24-59 | Verifier persona | Original | Unused in Micro-Mode pipeline |
| agents/personas.py SKEPTIC_PROMPT | 63-98 | Skeptic persona | Original | Unused in Micro-Mode pipeline |
| core/schemas.py SignalState | 21-56 | Signal evaluation | Original | Reserved for Phase 2, never instantiated |
| api_gateway/rate_limiter.py | 229 | _default_pool | Original | Shadowed when explicit pool is passed |
| api_gateway/__pycache__/provider_pool.cpython-313.pyc | — | provider_pool | Deleted | Stale bytecode from deleted module |
| orchestrator/__pycache__/judges.cpython-313.pyc | — | judges | Deleted | Stale bytecode from deleted module |

### 4.3 Duplicate Modules

| Module 1 | Module 2 | Duplication |
|----------|----------|-------------|
| core/security.py SecurityValidationError (line 51) | core/error_handlers.py SecurityValidationError (line 38) | Identical class defined twice |
| core/validators.py utc_now (line 26) | orchestrator/reasoning_graph.py _utc_now (line 25) | Same utility function |
| core/validators.py as_utc (line 35) | core/passport.py _as_utc (line 36) | Same utility function |
| core/validators.py iso_utc (line 58) | core/passport.py _iso_utc (line 41) | Same utility function |

### 4.4 Incorrect Layering

| Violation | File | Line | Description |
|-----------|------|------|-------------|
| Core imports orchestration | core/error_handlers.py | 244 | `from orchestrator.conversation import ConversationState` |
| Core imports orchestration | core/runtime.py | 291 | `from orchestrator.streaming import EventType, StreamEvent` |
| Server imports private | server.py | 43 | `from orchestrator.pipelines import _build_frontend_payload` |
| Core imports orchestration | core/error_handlers.py | 291 | `from orchestrator.streaming import EventType, StreamEvent` |

---

## 5. Separation of Concerns

### Assessment: FAIR

**Strengths:**
- ExecutionPassport cleanly separates request tracking from business logic
- SecurityValidator is a self-contained module with clear input/output contracts
- StreamingManager isolates SSE concerns from pipeline logic
- ProviderPool/ProviderStrategy cleanly abstract model routing

**Weaknesses:**
- `orchestrator/pipelines.py` combines prompt assembly, error handling, conversation management, claim extraction, and result formatting in 1152 lines
- `api_gateway/rate_limiter.py` combines ProviderPool, AsyncAPIGateway, ResourceManager, and TokenBucket — 4 distinct concerns
- `server.py` (771 lines) combines route definitions, request schemas, streaming logic, database initialization, and provider health management
- `core/runtime.py` combines contract management, contract validation, execution with contracts, and metrics tracking — could be split into 3 modules

---

## 6. SOLID Violations

### 6.1 Single Responsibility Principle (SRP)

| File | Violation | Classes/Responsibilities |
|------|-----------|-------------------------|
| api_gateway/rate_limiter.py | 4 classes, 1 file | ProviderPool (health tracking), ResourceManager (rate limiting), AsyncAPIGateway (execution), TokenBucket (algorithm) |
| orchestrator/pipelines.py | Dual pipeline paths | run_micro_mode and _run_with_decision_engine — two different pipeline orchestrations in one function |
| server.py | API + DB init + streaming | Route definitions, database initialization, SSE event generation, background task management |

### 6.2 Open/Closed Principle (OCP)

**Violations:**
- Provider strategy maps (FREE_MODELS, HYBRID_MODELS, PAID_MODELS) are hardcoded dicts — adding a new provider requires modifying `strategy.py`
- `api_gateway/client.py:61-91` has a long if/elif chain for provider URL routing — adding a new provider requires modifying this chain
- Pipeline stages cannot be extended without modifying `pipelines.py`

### 6.3 Liskov Substitution Principle (LSP)

**Violations:**
- `orchestrator/evaluation.py:33` returns `aetherisOutput | dict` — the caller must always check the return type (pipelines.py:331), violating substitutability

### 6.4 Interface Segregation Principle (ISP)

**Violations:**
- `StreamingManager` has 12 public methods — consumers typically need only 2-3. Could be split into `StreamWriter` (emit*) and `StreamReader` (iter*).
- `ProviderPool` has 20+ public methods — gateway consumers need only 4-5

### 6.5 Dependency Inversion Principle (DIP)

**Violations:**
- `AsyncAPIGateway` directly instantiates `AsyncHTTPClient` (rate_limiter.py:824) — should accept via constructor injection
- `orchestrator/pipelines.py` imports concrete implementations (AgentOutput, ProviderStrategy) rather than abstract interfaces
- No abstract base classes or protocols defined for any orchestrator component

---

## 7. Improper Coupling

| Type | Files | Description |
|------|-------|-------------|
| Content coupling | orchestrator/pipelines.py → api_gateway/rate_limiter.py | Accessing `pool._get_state()` (private method) from outside class |
| Content coupling | server.py → orchestrator/pipelines.py | Importing `_build_frontend_payload` (module-private function) |
| Stamp coupling | orchestrator/pipelines.py:302-308 | Passes full `gateway`, `strategy`, `pool` to `arbitrate_and_synthesize` when only execution is needed |
| Common coupling | orchestrator/memory.py:67 | Global mutable singleton `epistemic_memory` shared across modules |
| Common coupling | telemetry/observer.py:60 | Global mutable singleton `observer` shared across modules |
| Common coupling | core/config.py:189 | Global mutable singleton `_settings` shared across modules |

---

## 8. Missing Components

| Missing Component | Impact | Suggested Resolution |
|-------------------|--------|---------------------|
| Abstract provider interface | Cannot easily add new providers | Define `Provider` ABC with `execute()` method |
| Plugin system for pipeline stages | Pipeline is hardcoded, not extensible | Define `Stage` ABC with `execute()` hook |
| Database migrations | Schema changes require manual SQL | Add Alembic for migration management |
| API contract tests | Frontend-backend drift not detected | Add contract tests using OpenAPI schemas |
| Rate limiter integration tests | Circuit breaker logic untested | Add integration tests with mock providers |
| Observability dashboards | No real-time monitoring UI | Integrate with Prometheus/Grafana or build telemetry dashboard |
| Configuration validation at startup | Mismatched configs caught late | Add `check_config` CLI command |

---

## 9. Improper Naming

| File | Line | Current Name | Issue | Suggested Name |
|------|------|-------------|-------|----------------|
| orchestrator/pipelines.py | 375, 711, 1078 | `confidence_delta` | Measures confidence difference, not semantic diversity | Correct as is (was previously `diversity_metric` which was misleading) |
| orchestrator/pipelines.py | 368, 703, 1070 | `score_a`, `score_b` | Both set to same `validation_score` value | `logician_score`, `creative_score` |
| api_gateway/rate_limiter.py | 829 | `_default_pool` | Implies default behavior but is rarely used | `_fallback_pool` |
| core/error_handlers.py | 68 | `TimeoutError` | Shadows built-in `asyncio.TimeoutError` | `ExecutionTimeoutError` |

---

## 10. Detailed Issue Register

---

### CRIT-001: Dual Execution Paths in pipelines.py

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Category** | Architecture |
| **Status** | 🔴 Open |
| **File** | orchestrator/pipelines.py |
| **Approximate Line Number** | 72-448 (legacy), 798-1148 (DecisionEngine) |
| **Class** | — (module-level functions) |
| **Function** | `run_micro_mode`, `stream_micro_mode`, `_run_with_decision_engine` |
| **Description** | `pipelines.py` contains two complete and independent execution paths for the micro-mode pipeline. The legacy inline path (lines 72-448) directly calls gateway, parser, and evaluation functions. The DecisionEngine path (lines 798-1148) delegates to `decisions.py`. Both paths produce the same result type (`MicroModeResult`) but use different internal logic, creating maintenance burden and risk of behavioral divergence. |
| **Expected Behaviour** | A single execution path should implement the pipeline. The DecisionEngine refactor should either fully replace the legacy path or be the sole path. |
| **Current Behaviour** | `run_micro_mode` checks if `decision_engine` is not None and forks into the DecisionEngine path; otherwise falls through to the legacy path. Both paths contain duplicated conversation management, error handling, claim extraction, and result assembly logic. |
| **Impact** | High. Dual paths double the maintenance surface. Bug fixes must be applied in both places. Behavioral differences between paths are not tested. |
| **Root Cause** | Incremental refactoring — the DecisionEngine was introduced without removing the legacy path. |
| **Suggested Resolution** | Remove the legacy inline path (lines 122-444 and 484-724) entirely, making the DecisionEngine path the sole implementation. Extract shared utilities (conversation handling, claim extraction, result assembly) into helper functions. |
| **Dependencies** | orchestrator/decisions.py, orchestrator/evaluation.py |
| **Estimated Complexity** | High (2-3 weeks) |
| **Related Issues** | HIGH-009 (unused RuntimeEngine), HIGH-003 (unused pipeline_scheduler.py) |

---

### CRIT-002: Missing Test Suite for Orchestration Logic

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Category** | Testing |
| **Status** | 🔴 Open |
| **File** | (project-wide) |
| **Approximate Line Number** | — |
| **Class** | — |
| **Function** | — |
| **Description** | No automated pytest tests exist for the core orchestration logic: DecisionEngine, PipelineScheduler, ConversationDirector, SecurityValidator, ClaimManager, StreamingManager, or ExecutionPassport. Frontend vitest tests exist but cover only utility functions and store logic. Backend has no test directory, no pytest configuration, and no test files. |
| **Expected Behaviour** | Core orchestration components should have unit tests verifying state transitions, error handling, edge cases, and integration behavior. |
| **Current Behaviour** | No tests. Refactoring or modifying any core component risks regression without detection. |
| **Impact** | High. Any refactoring (e.g., CRIT-001 resolution, HIGH-002 consolidation) is high-risk without test coverage. |
| **Root Cause** | Tests were deprioritized during development. |
| **Suggested Resolution** | Create `tests/` directory with pytest configuration. Implement unit tests for ExecutionPassport, SecurityValidator, ConversationDirector, DecisionEngine, StreamingManager, ClaimManager. Add integration tests for pipeline execution with mocks. |
| **Dependencies** | pytest, pytest-asyncio, pytest-cov |
| **Estimated Complexity** | High (2-3 weeks) |
| **Related Issues** | CRIT-001, HIGH-003, MED-006 |

---

### CRIT-003: Incomplete Checkpoint Storage Backends

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Category** | Architecture |
| **Status** | 🔴 Open |
| **File** | orchestrator/checkpoints.py |
| **Approximate Line Number** | 257-259, 271-273, 294-296, 319-321 |
| **Class** | CheckpointManager |
| **Function** | `_store_checkpoint`, `_retrieve_checkpoint`, `_list_checkpoints_impl`, `_expire_checkpoints_impl` |
| **Description** | Four storage backend methods unconditionally raise `NotImplementedError` for `filesystem` and `database` backends. Only the `memory` backend is implemented. Since checkpoints are in-memory only, they are lost on server restart, defeating the purpose of checkpoint-based recovery. |
| **Expected Behaviour** | At minimum, the `filesystem` backend should be functional so checkpoints survive restarts. The `database` backend should use the existing SQLAlchemy async engine. |
| **Current Behaviour** | `raise NotImplementedError(f"Storage backend '{self.storage_backend}' not yet implemented")` for any non-memory backend. |
| **Impact** | High. Checkpoint-based pipeline recovery is effectively non-functional in any production scenario. |
| **Root Cause** | Checkpoint feature was implemented incrementally; persistent backends were deferred. |
| **Suggested Resolution** | Implement filesystem backend using JSON file storage in a configurable directory. Implement database backend using SQLAlchemy models and the existing async engine. |
| **Dependencies** | core/database.py, core/models.py |
| **Estimated Complexity** | Medium (1-2 weeks) |
| **Related Issues** | MED-007 (in-memory sessions) |

---

### HIGH-001: Real API Keys Committed in .env

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Security |
| **Status** | 🔴 Open |
| **File** | .env |
| **Approximate Line Number** | 1-15 |
| **Class** | — |
| **Function** | — |
| **Description** | The `.env` file contains 9 real provider API keys (OpenRouter, NVIDIA NIM, Groq, GitHub, Mistral, Google, OpenAI, Kie, UNLI). These keys have a monetary cost associated with each API call. If committed to a public repository, they could be harvested and abused. |
| **Expected Behaviour** | API keys should never be stored in the repository. Default to empty strings in `.env.example` and load from environment variables. |
| **Current Behaviour** | Real keys are present in `.env` at the repository root. While `.env` is in `.gitignore`, if the file was ever committed or shared, keys are exposed. |
| **Impact** | High. Potential financial loss from unauthorized API usage. Each key provides access to paid LLM services. |
| **Root Cause** | Development convenience — keys were placed in .env for local testing. |
| **Suggested Resolution** | Immediately rotate all API keys at their respective providers. Remove real keys from `.env` and replace with empty strings. Use `.env.example` with placeholder values as documented. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | — |

---

### HIGH-002: Duplicate SecurityValidationError

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Architecture |
| **Status** | 🔴 Open |
| **File** | core/security.py (line 51), core/error_handlers.py (line 38) |
| **Approximate Line Number** | core/security.py:51-73, core/error_handlers.py:38-48 |
| **Class** | SecurityValidationError |
| **Function** | — |
| **Description** | The `SecurityValidationError` exception class is defined identically in two separate modules. `core/security.py:51` defines it as a subclass of `ValueError`. `core/error_handlers.py:38` defines it as a subclass of `AETHERISException`. These are different types, so except handlers for one will not catch the other. |
| **Expected Behaviour** | A single canonical `SecurityValidationError` should be defined in one place and imported by all consumers. |
| **Current Behaviour** | Two definitions exist. `core/runtime.py:325` imports from `core.security` (ValueError subclass). `api_gateway/rate_limiter.py:24-26` imports from `core.security` (also the ValueError subclass). The `error_handlers.py` version is never imported anywhere — it is dead code. However, its existence creates confusion and potential for incorrect imports. |
| **Impact** | High. If a consumer imports from the wrong module, exception handling may silently fail, allowing security violations to propagate uncaught. |
| **Root Cause** | Refactoring — `error_handlers.py` was created later and duplicated the class without removing the original. |
| **Suggested Resolution** | Remove the duplicate in `core/error_handlers.py:38-48`. Ensure all consumers import from `core.security`. |
| **Dependencies** | core/security.py, core/error_handlers.py |
| **Estimated Complexity** | Low (2-3 days) |
| **Related Issues** | — |

---

### HIGH-003: Unused pipeline_scheduler.py Module

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Dead Code |
| **Status** | 🔴 Open |
| **File** | orchestrator/pipeline_scheduler.py |
| **Approximate Line Number** | 1-679 |
| **Class** | PipelineScheduler |
| **Function** | `execute_pipeline`, `execute_stage`, `execute_parallel_agents`, `handle_stage_failure`, `emit_stage_transition` |
| **Description** | A complete 679-line module implementing a full `PipelineScheduler` class with stage orchestration, state machine integration, and parallel agent execution. This module is never imported or used by any entry point (`main.py`, `server.py`, or any orchestrator `__init__.py`). It is not re-exported from `orchestrator/__init__.py`. |
| **Expected Behaviour** | Either the pipeline scheduler should be integrated into the execution flow, or the dead code should be removed. |
| **Current Behaviour** | The module exists on disk but is completely unreachable at runtime. It represents either a planned future feature or leftover code from a refactoring. |
| **Impact** | High. 679 lines of dead code represent maintenance burden and confusion for developers. |
| **Root Cause** | Refactoring — the DecisionEngine path was introduced, making the PipelineScheduler redundant. |
| **Suggested Resolution** | Either (a) wire PipelineScheduler into the execution path via `orchestrator/__init__.py` and replace the DecisionEngine, or (b) remove the file entirely. Option (a) is recommended if the scheduler provides functionality not in the DecisionEngine. |
| **Dependencies** | orchestrator/state_machine.py, orchestrator/streaming.py |
| **Estimated Complexity** | Low (1-2 days to evaluate and either integrate or remove) |
| **Related Issues** | CRIT-001, HIGH-009 |

---

### HIGH-004: Private Method Access from Outside Class

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Improper Coupling |
| **Status** | 🟠 Open |
| **File** | orchestrator/pipelines.py, api_gateway/rate_limiter.py |
| **Approximate Line Number** | pipelines.py:~907, rate_limiter.py:906-908 |
| **Class** | AsyncAPIGateway |
| **Function** | `execute_with_fallback` |
| **Description** | `AsyncAPIGateway.execute_with_fallback` accesses `pool._get_state(provider_name)` — a private method of `ProviderPool` — from outside the class. The public equivalent `pool.get_status()` exists and provides the same data. |
| **Expected Behaviour** | Code outside a class should not access private (underscore-prefixed) methods. The public API should be used. |
| **Current Behaviour** | `pool._get_state(provider_name)` is called at line 907 of `rate_limiter.py` to check error count against degradation threshold. If the private method is renamed or removed, this call breaks silently. |
| **Impact** | High. The private method is not part of the public API contract. Renaming or changing its signature during refactoring will break this call site. |
| **Root Cause** | Developer overlooked the public equivalent. |
| **Suggested Resolution** | Replace `pool._get_state(provider_name)` with `pool.get_status(provider_name)` and access error count from the returned dict. |
| **Dependencies** | api_gateway/rate_limiter.py |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | LOW-004 |

---

### HIGH-005: Hardcoded Windows PostgreSQL Paths

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Portability |
| **Status** | 🟠 Open |
| **File** | server.py |
| **Approximate Line Number** | 99-101 |
| **Class** | — (lifespan function) |
| **Function** | `lifespan` |
| **Description** | The FastAPI lifespan function includes hardcoded paths to Windows-specific PostgreSQL executables and data directories: `C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe` and `C:\Program Files\PostgreSQL\18\data`. This code attempts to auto-start PostgreSQL if the initial connection fails. These paths are specific to one OS, one PostgreSQL version, and one installation location. |
| **Expected Behaviour** | Database startup should not be managed by the application. The application should fail gracefully with a clear error message if the database is unavailable. |
| **Current Behaviour** | On database connection failure, the server attempts to start PostgreSQL via subprocess using hardcoded paths. This will fail silently on any non-Windows system or any PostgreSQL installation in a different location. |
| **Impact** | High. The application silently swallows database failures and attempts to execute OS commands with hardcoded paths that will only work in one environment. |
| **Root Cause** | Development convenience for a specific local setup. |
| **Suggested Resolution** | Remove the auto-start PostgreSQL logic entirely. Log a clear error message with instructions to start PostgreSQL manually. Document the database requirement in deployment docs. |
| **Dependencies** | core/database.py |
| **Estimated Complexity** | Low (1 day) |
| **Related Issues** | — |

---

### HIGH-006: Unused Persona Prompts

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Dead Code |
| **Status** | 🟠 Open |
| **File** | agents/personas.py |
| **Approximate Line Number** | 24-98 |
| **Class** | — (module-level constants) |
| **Function** | — |
| **Description** | `VERIFIER_PROMPT` (lines 24-59) and `SKEPTIC_PROMPT` (lines 63-98) are defined in the persona registry but are never referenced in any prompt assembly or pipeline logic. Only `LOGICIAN_PROMPT`, `CREATIVE_PROMPT`, and `BREAKER_PROMPT` are used by the current Micro-Mode pipeline. |
| **Expected Behaviour** | Only used personas should be defined in the source code. Unused personas create confusion about the intended agent architecture. |
| **Current Behaviour** | Two complete system prompts (95 lines total) exist but are never loaded, referenced, or assigned to any agent role in the pipeline. |
| **Impact** | Medium. Maintainers may incorrectly assume these personas are active in the pipeline. |
| **Root Cause** | Legacy from original Multi-Agent Reflexion (MAR) architecture — the Micro-Mode pipeline uses only Breaker, Logician, Creative, and Judge agents. |
| **Suggested Resolution** | Either (a) remove VERIFIER_PROMPT and SKEPTIC_PROMPT, or (b) move them to a separate file (`personas_extended.py`) with documentation explaining they are reserved for future use. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | — |

---

### HIGH-007: Unused SignalState Schema

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Dead Code |
| **Status** | 🟠 Open |
| **File** | core/schemas.py |
| **Approximate Line Number** | 21-56 |
| **Class** | SignalState |
| **Function** | — |
| **Description** | The `SignalState` Pydantic model is defined with strict validation (frozen=True) for real-time evaluation metrics. The docstring explicitly states it is "Currently unused in the Micro-Mode pipeline (Phase 1)." No module in the current codebase imports or instantiates `SignalState`. |
| **Expected Behaviour** | Schema definitions used in Phase 2 should be in a separate extension file or clearly marked as experimental. |
| **Current Behaviour** | `SignalState` lives alongside active schemas (`AgentOutput`, `aetherisOutput`, `PipelineResult`) in `core/schemas.py`, creating the impression it is part of the active data contract. |
| **Impact** | Medium. Developers may mistakenly think signal evaluation is active. Schema changes to active models could be misapplied. |
| **Root Cause** | Forward-looking design added before implementation. |
| **Suggested Resolution** | Either (a) remove SignalState entirely, (b) move to `core/schemas_extensions.py`, or (c) implement Phase 1 integration so it's no longer dead code. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | HIGH-006 |

---

### HIGH-008: Frontend-Backend Session State Divergence

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Architecture |
| **Status** | 🟠 Open |
| **File** | aetheris-ui/src/store/useChatStore.js, server.py |
| **Approximate Line Number** | useChatStore.js:1-131, server.py:511-600 |
| **Class** | — (store module) |
| **Function** | — |
| **Description** | The frontend manages conversation history entirely in client-side `localStorage` via Zustand (`useChatStore`). The backend has a complete session management system (`ConversationDirector` in `orchestrator/conversation.py`) with session creation, history tracking, state transitions, and truncation. The frontend never calls backend session endpoints (`/api/sessions`, `/api/sessions/{id}/history`). |
| **Expected Behaviour** | Session state should be authoritative on the server. The frontend should delegate conversation history management to the backend. |
| **Current Behaviour** | Frontend stores all conversation state in localStorage. Backend sessions are created per-query with one-shot UUIDs (server.py:319) but never persisted or retrieved across requests. The comment in useChatStore.js:10-11 explicitly acknowledges this: "The backend spec defines no conversation-persistence endpoint." |
| **Impact** | High. Conversation history is lost if localStorage is cleared or users switch browsers. Backend session management infrastructure is completely unused from the frontend. |
| **Root Cause** | Missing integration — backend session endpoints exist but frontend never calls them. |
| **Suggested Resolution** | (1) Frontend should call `/api/sessions` on app load to create a backend session. (2) Each query should include the `session_id`. (3) History should be fetched from `/api/sessions/{id}/history` on conversation selection. (4) Use localStorage as a fallback cache, not the primary store. |
| **Dependencies** | aetheris-ui/src/api/client.js, orchestrator/conversation.py |
| **Estimated Complexity** | Medium (1-2 weeks) |
| **Related Issues** | MED-007 |

---

### HIGH-009: RuntimeEngine.execute_with_contracts Never Called

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Dead Code |
| **Status** | 🟠 Open |
| **File** | core/runtime.py |
| **Approximate Line Number** | 236-506 |
| **Class** | RuntimeEngine |
| **Function** | `execute_with_contracts`, `validate_contracts` |
| **Description** | The `RuntimeEngine` class provides a sophisticated `execute_with_contracts` method (270 lines) that validates security contracts, enforces rate limits, emits streaming events, tracks execution metrics, and handles timeouts. However, this method is never called by any pipeline code. The pipeline calls `gateway.execute_with_fallback()` directly, bypassing the runtime engine entirely. |
| **Expected Behaviour** | All agent executions should go through `RuntimeEngine.execute_with_contracts` to enforce contracts consistently. |
| **Current Behaviour** | Both pipeline paths (legacy and DecisionEngine) call `gateway.execute_with_fallback()` directly. The RuntimeEngine is instantiated by `initialize_aetheris_components` but never referenced again. |
| **Impact** | High. The entire contract enforcement layer (security validation, rate limiting, streaming, metrics tracking) is bypassed. |
| **Root Cause** | Refactoring — RuntimeEngine was added after the pipeline was working and never integrated. |
| **Suggested Resolution** | Refactor `execute_with_fallback` or add a wrapper in `AsyncAPIGateway` that calls `RuntimeEngine.execute_with_contracts`. Alternatively, make `RuntimeEngine` the primary entry point for all agent calls. |
| **Dependencies** | core/runtime.py, api_gateway/rate_limiter.py |
| **Estimated Complexity** | Medium (1-2 weeks) |
| **Related Issues** | CRIT-001, HIGH-003 |

---

### HIGH-010: Naive Datetime in StreamEvent

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | Data Integrity |
| **Status** | 🟠 Open |
| **File** | orchestrator/streaming.py |
| **Approximate Line Number** | 64-65 |
| **Class** | StreamEvent |
| **Function** | — |
| **Description** | `StreamEvent.timestamp` uses `datetime.utcnow()` as the default factory, which returns a naive datetime (no timezone info). All other datetime fields in the codebase (ExecutionPassport, ConversationDirector, CheckpointManager) use timezone-aware UTC datetimes. This inconsistency can cause comparison errors and serialization issues. |
| **Expected Behaviour** | All datetime fields should use timezone-aware UTC datetimes consistently. |
| **Current Behaviour** | `StreamEvent.timestamp` defaults to a naive datetime. The `to_dict()` method calls `.isoformat()` on it, producing `2026-06-27T12:00:00` instead of `2026-06-27T12:00:00+00:00`. |
| **Impact** | Medium. Timestamps in SSE events lack timezone information. Consumers cannot reliably compare or sort events across timezones. |
| **Root Cause** | Developer oversight — used `datetime.utcnow()` instead of `datetime.now(timezone.utc)`. |
| **Suggested Resolution** | Replace `datetime.utcnow` with `datetime.now(timezone.utc)` or use `core.validators.utc_now()`. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (30 minutes) |
| **Related Issues** | — |

---

### MED-001: Private Function Imported Across Modules

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Improper Coupling |
| **Status** | 🟡 Open |
| **File** | server.py |
| **Approximate Line Number** | 43 |
| **Class** | — |
| **Function** | — |
| **Description** | `server.py:43` imports `_build_frontend_payload` from `orchestrator.pipelines`. The underscore prefix conventionally indicates a module-private function. This function is used in server.py to convert `MicroModeResult` dicts into frontend-expected shapes. |
| **Expected Behaviour** | Public functions should be used across module boundaries. Private functions should only be used within their defining module. |
| **Current Behaviour** | A private function is imported and used across package boundaries. |
| **Impact** | Medium. If the private function is renamed or refactored (its signature changed), server.py breaks. Since it's not part of the public API, this can happen without warning. |
| **Root Cause** | The function was not promoted to the public API when the frontend contract boundary was created. |
| **Suggested Resolution** | Rename `_build_frontend_payload` to `build_frontend_payload` (remove underscore) and add it to `orchestrator/__init__.py` exports. Or move it to a shared utility module. |
| **Dependencies** | orchestrator/pipelines.py |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | HIGH-004 |

---

### MED-002: Mode Not Passed to Stream Pipeline

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Data Integrity |
| **Status** | 🟡 Open |
| **File** | orchestrator/pipelines.py |
| **Approximate Line Number** | 84, 453 |
| **Function** | `stream_micro_mode` |
| **Description** | `stream_micro_mode` does not accept a `strategy` or `mode` parameter. It calls `assemble_generation_prompts(strategy.mode.value)` at line 485, but `strategy` is a parameter of `stream_micro_mode`. However, `server.py:376-470` creates the `ProviderStrategy` at initialization time with mode "HYBRID" (line 114) and never allows overriding. The streaming pipeline always uses HYBRID mode regardless of the `--mode` or `strategy` configuration. |
| **Expected Behaviour** | The streaming pipeline should respect the configured strategy mode. |
| **Current Behaviour** | `stream_micro_mode` always uses the strategy object passed by `server.py`, which is always `HYBRID`. |
| **Impact** | Medium. The streaming pipeline cannot use FREE or PAID modes. |
| **Root Cause** | The mode parameter was not plumbed through from configuration to the streaming endpoint. |
| **Suggested Resolution** | Pass the mode from `server.py`'s configuration to `stream_micro_mode`. Consider accepting a `mode` parameter in the stream API endpoint. |
| **Dependencies** | server.py |
| **Estimated Complexity** | Low (half day) |
| **Related Issues** | — |

---

### MED-003: Duplicate Streaming Event Emission Patterns

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Code Quality |
| **Status** | 🟡 Open |
| **File** | core/runtime.py |
| **Approximate Line Number** | 290-325, 340-353, 363-376, 408-423, 447-461, 483-497 |
| **Class** | RuntimeEngine |
| **Function** | `execute_with_contracts` |
| **Description** | The `execute_with_contracts` method contains 6+ blocks of nearly identical code that construct `StreamEvent` objects and call `self.streaming_manager.emit_event()`. Each block imports `EventType` and `StreamEvent` from `orchestrator.streaming` inside the method body. These blocks handle INJECTION_DETECTED, VALIDATION_FAILED, RATE_LIMIT_EXCEEDED, AGENT_STARTED, AGENT_COMPLETED, and ERROR events. |
| **Expected Behaviour** | Event emission should be DRY — a single helper or pattern should handle all event types. |
| **Current Behaviour** | Each event type has its own block with identical boilerplate: import, construct, emit. |
| **Impact** | Medium. 100+ lines of duplicated code. Adding a new event type requires copying the same pattern. |
| **Root Cause** | Incremental development — each event was added independently. |
| **Suggested Resolution** | Create a helper method `_emit_stream_event(event_type, data)` on RuntimeEngine that handles the import and emission. Replace all 6+ blocks with calls to this helper. |
| **Dependencies** | core/runtime.py, orchestrator/streaming.py |
| **Estimated Complexity** | Low (half day) |
| **Related Issues** | — |

---

### MED-004: Duplicate Conversation State Transition Blocks

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Code Quality |
| **Status** | 🟡 Open |
| **File** | orchestrator/pipelines.py |
| **Approximate Line Number** | 129-149, 216-234, 236-254, 301-320, 329-347, 496-512, 583-593 |
| **Function** | `run_micro_mode`, `stream_micro_mode` |
| **Description** | At least 8 locations in `pipelines.py` contain identical 5-8 line blocks that: (1) check if `conversation_director` and `session_id` are not None, (2) import `ConversationState` inside the block, (3) call `transition_state(session_id, ConversationState.FAILED)`, (4) catch and suppress all exceptions. The `transition_conversation_to_failed` helper in `core/error_handlers.py:223-249` was created to eliminate this duplication but is not used consistently. |
| **Expected Behaviour** | A single `transition_conversation_to_failed()` call should replace each block. |
| **Current Behaviour** | 8 blocks of identical code. |
| **Impact** | Medium. Any change to error handling logic must be applied in 8 places. |
| **Root Cause** | The helper was added after the duplicate blocks were written, and not all call sites were updated. |
| **Suggested Resolution** | Replace all 8 blocks with calls to `transition_conversation_to_failed(conversation_director, session_id, logger)`. |
| **Dependencies** | core/error_handlers.py |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | — |

---

### MED-005: Duplicate StreamingManager Emission Methods

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Code Quality |
| **Status** | 🟡 Open |
| **File** | orchestrator/streaming.py |
| **Approximate Line Number** | 302-316, 318-343 |
| **Class** | StreamingManager |
| **Function** | `emit`, `emit_raw` |
| **Description** | `StreamingManager` has three methods for emitting events: `emit_event` (line 168, takes StreamEvent), `emit` (line 302, takes EventType + dict), and `emit_raw` (line 318, takes raw dict). The `emit` and `emit_raw` methods duplicate the logic of constructing a `StreamEvent` and delegating to `emit_event`. `emit_raw` additionally handles event type string parsing that duplicates logic in `server.py:408-416`. |
| **Expected Behaviour** | A single emission method should be the canonical path. |
| **Current Behaviour** | Three methods with overlapping functionality. Callers are split between `emit` and `emit_event` inconsistently. |
| **Impact** | Medium. Maintenance burden and potential for inconsistent event handling. |
| **Root Cause** | The API grew organically with different consumer needs. |
| **Suggested Resolution** | Deprecate `emit` and `emit_raw` in favor of `emit_event`. Update all callers. Alternatively, keep `emit` as the public API and make `emit_event` private. |
| **Dependencies** | orchestrator/streaming.py |
| **Estimated Complexity** | Low (half day) |
| **Related Issues** | MED-003 |

---

### MED-006: Claim Validation Is Placeholder

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Architecture |
| **Status** | 🟡 Open |
| **File** | orchestrator/claims.py |
| **Approximate Line Number** | 168-184 |
| **Class** | ClaimManager |
| **Function** | `validate_claim` |
| **Description** | `ClaimManager.validate_claim` unconditionally sets `validation_status` to `UNVERIFIED` and `confidence` to `0.3` for every claim. The docstring explicitly states this is a "Phase 1 placeholder." Despite over 100 lines being extracted, classified, stored, and tracked in every pipeline run, the validation step produces zero actionable information — every claim is always `UNVERIFIED`. |
| **Expected Behaviour** | Claims should be validated against a knowledge source (Wikipedia API, fact-checking service, or cross-referencing with other agent outputs). |
| **Current Behaviour** | All claims are assigned `UNVERIFIED` with `confidence=0.3`. The claim extraction and tracking pipeline runs in full (extracting claims from 4 agents, classifying, storing in ReasoningGraph, tracking provenance), but the validation step is a no-op. |
| **Impact** | Medium. Claim extraction creates processing overhead without delivering value. The "unverified claims" count in responses is always equal to the total extracted claims, providing no useful signal. |
| **Root Cause** | Placeholder implementation deferred to Phase 2. |
| **Suggested Resolution** | Either (a) implement basic cross-referencing validation (compare claims between agents for agreement/contradiction), or (b) disable claim extraction entirely and re-enable when validation is implemented. |
| **Dependencies** | None |
| **Estimated Complexity** | Medium (1-2 weeks for basic cross-referencing) |
| **Related Issues** | — |

---

### MED-007: In-Memory Session Storage Not Persisted

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Architecture |
| **Status** | 🟡 Open |
| **File** | orchestrator/conversation.py |
| **Approximate Line Number** | 92 |
| **Class** | ConversationDirector |
| **Function** | `__init__` |
| **Description** | `ConversationDirector` stores all session data in an in-memory dictionary (`self._sessions: dict[str, ConversationSession]`). Sessions are lost on server restart, process crash, or deployment. There is no database persistence or serialization to disk. |
| **Expected Behaviour** | Session data should persist across server restarts using the existing PostgreSQL database via SQLAlchemy. |
| **Current Behaviour** | All session history, state transitions, and metadata exist only in process memory. |
| **Impact** | Medium. Multi-turn conversations cannot survive server restart. Users lose conversation history on any deployment or crash. |
| **Root Cause** | Session management was implemented for in-memory use only. Database persistence was deferred. |
| **Suggested Resolution** | Add a SQLAlchemy-backed session store to `ConversationDirector` using the existing `core/database.py` engine and `core/models.py` User model. |
| **Dependencies** | core/database.py, core/models.py |
| **Estimated Complexity** | Medium (1-2 weeks) |
| **Related Issues** | CRIT-003, HIGH-008 |

---

### MED-008: Login Page Served from Root Level

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Organization |
| **Status** | 🟡 Open |
| **File** | server.py |
| **Approximate Line Number** | 257-262 |
| **Class** | — |
| **Function** | `serve_login` |
| **Description** | The login page is served from `Path(__file__).parent / "aetheris_login.html"` — a file at the repository root rather than inside `aetheris-ui/` where all other frontend assets live. This file (538KB) contains a large inline HTML/CSS/JS application that duplicates the Vite-built React frontend's login functionality. |
| **Expected Behaviour** | All frontend assets should be served from `aetheris-ui/dist/` or `aetheris-ui/src/`. |
| **Current Behaviour** | A separate, non-Vite-built login page exists at the repository root. It appears to be a standalone HTML page, not built through the Vite pipeline. |
| **Impact** | Medium. Two separate login implementations to maintain. The root-level HTML file bypasses the frontend build system, making it inconsistent with the rest of the UI. |
| **Root Cause** | The login page was created before the Vite frontend was built or as a workaround. |
| **Suggested Resolution** | Integrate the login page into the Vite React app. Remove the root-level `aetheris_login.html` file and serve login from `aetheris-ui/dist/login.html`. |
| **Dependencies** | aetheris-ui |
| **Estimated Complexity** | Low (half day) |
| **Related Issues** | — |

---

### MED-009: Placeholder Embeddings in ReasoningGraph

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Architecture |
| **Status** | 🟡 Open |
| **File** | orchestrator/reasoning_graph.py |
| **Approximate Line Number** | 199-220 |
| **Class** | ReasoningGraph |
| **Function** | `_placeholder_embedding` |
| **Description** | The `_placeholder_embedding` method generates a 26-dimensional vector based purely on character frequency (a-z). This is not a semantic embedding — text with completely different meanings but similar letter distributions could be considered "similar." The docstring acknowledges this is a Phase 1 placeholder. All similarity-based queries (find_similar_nodes, get_failure_patterns) use this flawed embedding or simple substring matching. |
| **Expected Behaviour** | Semantic similarity should use proper embeddings (e.g., sentence-transformers, OpenAI embeddings API). |
| **Current Behaviour** | Similarity is based on letter frequency (26-dim character histogram) or substring containment. Neither approach captures semantic meaning. |
| **Impact** | Medium. Failure pattern matching may retrieve irrelevant patterns while missing relevant ones, reducing the value of epistemic memory. |
| **Root Cause** | Placeholder implementation to avoid external embedding dependencies in Phase 1. |
| **Suggested Resolution** | Integrate with sentence-transformers for local embeddings or the configured LLM provider for API-based embeddings. |
| **Dependencies** | None (optional: sentence-transformers) |
| **Estimated Complexity** | Medium (1 week) |
| **Related Issues** | MED-006 |

---

### MED-010: Duplicate Field-Mapping Logic in Schemas

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Code Quality |
| **Status** | 🟡 Open |
| **File** | core/schemas.py |
| **Approximate Line Number** | 76-137, 177-214 |
| **Class** | AgentOutput, aetherisOutput |
| **Function** | `map_contract_fields` (both classes) |
| **Description** | Both `AgentOutput` and `aetherisOutput` define `model_validator(mode="before")` methods named `map_contract_fields` that resolve alternative field names into canonical schema fields. The duplication includes mapping XML response contract fields to standard fields, converting confidence levels, and providing default values. The `core/validators.py:467-500` `resolve_field` helper was created to deduplicate this logic but is only partially used. |
| **Expected Behaviour** | Field resolution logic should be shared between both schemas. |
| **Current Behaviour** | Each schema has its own copy of the field-mapping logic (approximately 60 lines each). |
| **Impact** | Medium. Adding a new alternative field name requires updating both schemas. |
| **Root Cause** | Schemas were developed independently before the shared utility was created. |
| **Suggested Resolution** | Refactor `map_contract_fields` in both schemas to use shared helpers from `core/validators.py`. Consolidate confidence mapping into a single `_resolve_confidence` helper. |
| **Dependencies** | core/validators.py |
| **Estimated Complexity** | Low (half day) |
| **Related Issues** | — |

---

### MED-011: AsyncAPIGateway Bypasses Dependency Injection

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Architecture |
| **Status** | 🟡 Open |
| **File** | api_gateway/rate_limiter.py |
| **Approximate Line Number** | 822, 828 |
| **Class** | AsyncAPIGateway |
| **Function** | `__init__` |
| **Description** | `AsyncAPIGateway.__init__` accepts an optional `client` parameter (for dependency injection) but falls back to `client or AsyncHTTPClient()`. In both `main.py` and `server.py`, the gateway is created with default arguments: `gateway = AsyncAPIGateway()` — meaning a new `AsyncHTTPClient` is always created without any injected dependencies. The `AsyncHTTPClient` constructor also has an optional `security_validator` parameter (client.py:19) that is never injected. |
| **Expected Behaviour** | Dependencies should be injected at construction time to allow testing with mocks and to share configured instances. |
| **Current Behaviour** | Both `AsyncAPIGateway` and `AsyncHTTPClient` are always created with default arguments, losing the opportunity for dependency injection. |
| **Impact** | Medium. Testing with mocked HTTP calls requires monkey-patching or additional indirection. |
| **Root Cause** | Entry points (`main.py`, `server.py`) use default arguments for convenience. |
| **Suggested Resolution** | Update `main.py` and `server.py` to explicitly construct and inject dependencies: `client = AsyncHTTPClient(security_validizer=sv); gateway = AsyncAPIGateway(client=client)`. |
| **Dependencies** | main.py, server.py |
| **Estimated Complexity** | Low (half day) |
| **Related Issues** | MED-012 |

---

### MED-012: Fire-and-Forget asyncio.create_task for Streaming Events

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Concurrency |
| **Status** | 🟡 Open |
| **File** | orchestrator/decisions.py |
| **Approximate Line Number** | 160-166, 174-181, 213-219, 289-295 |
| **Class** | DecisionEngine |
| **Function** | `execute_breaker_gate`, `execute_generation_agents`, `execute_judge_synthesis` |
| **Description** | `asyncio.create_task()` is used to emit streaming events in a fire-and-forget manner at 4+ locations. The created tasks are never stored, awaited, or have error handlers attached. If an event emission fails (e.g., queue full), the exception is silently lost because no task-level exception handling exists. |
| **Expected Behaviour** | Background tasks should have error handlers attached via `task.add_done_callback()` or be properly awaited. |
| **Current Behaviour** | Tasks are created and forgotten. Exceptions raised in these tasks are silently swallowed. |
| **Impact** | Medium. Silent failures in event emission mean the frontend may miss streaming events without any error indication. |
| **Root Cause** | Developer convenience — fire-and-forget is simpler than proper task management. |
| **Suggested Resolution** | Attach an error-handling callback: `task.add_done_callback(lambda t: logger.error("Stream event failed", exc_info=t.exception()) if t.exception() else None)`. |
| **Dependencies** | orchestrator/streaming.py |
| **Estimated Complexity** | Low (half day) |
| **Related Issues** | MED-005 |

---

### MED-013: Semaphore Handling Bug in ResourceManager

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | Concurrency |
| **Status** | 🟡 Open |
| **File** | api_gateway/rate_limiter.py |
| **Approximate Line Number** | 654-655 |
| **Class** | ResourceManager |
| **Function** | `acquire_resources` |
| **Description** | The `acquire_resources` method has a bug in global semaphore handling: `self.global_semaphore.release() if self.global_semaphore.locked() else None` releases the semaphore without having acquired it first, followed by an attempt to acquire with a short timeout. This pattern is incorrect — it unconditionally releases a permit from the semaphore (even if none was acquired), then tries to immediately re-acquire it. This can inflate the semaphore's permit count over time. |
| **Expected Behaviour** | The semaphore should be acquired once per request via `await self.global_semaphore.acquire()` and released after completion. |
| **Current Behaviour** | The semaphore is released unconditionally (inflating permit count), then acquired with a 1ms timeout. If the timeout expires, tokens are refunded but the extra release has already happened. |
| **Impact** | Medium. Over time, the global semaphore can accumulate excess permits, allowing more concurrent requests than the configured limit of 100. |
| **Root Cause** | Buggy implementation — likely intended to check if semaphore is available, but the release+acquire pattern is incorrect. |
| **Suggested Resolution** | Replace with a non-blocking acquire pattern: `acquired = self.global_semaphore.acquire() if not self.global_semaphore.locked() else True`. Or simply use `await self.global_semaphore.acquire()` (blocking) which is the standard pattern. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | — |

---

### LOW-001: Telemetry Uses print() Instead of Logger

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Code Quality |
| **Status** | 🟢 Open |
| **File** | telemetry/observer.py |
| **Approximate Line Number** | 51-58 |
| **Class** | TelemetryObserver |
| **Function** | `print_session_report` |
| **Description** | `print_session_report` uses `print()` to emit telemetry session reports. This bypasses the configured logging system, meaning output cannot be filtered by log level, redirected to files, or formatted consistently. In web server mode, `print()` writes directly to stdout instead of through the structured uvicorn logger. |
| **Expected Behaviour** | All telemetry output should use `logger.info()` for consistent routing. |
| **Current Behaviour** | 8 `print()` calls in `print_session_report`. |
| **Impact** | Low. Telemetry is still visible but not properly integrated with the logging system. |
| **Root Cause** | Original implementation used `print()` for simplicity. |
| **Suggested Resolution** | Replace all `print()` calls with `logger.info()`. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (30 minutes) |
| **Related Issues** | — |

---

### LOW-002: Confidence Delta Naming (Historical)

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Naming |
| **Status** | 🟢 Open |
| **File** | orchestrator/pipelines.py |
| **Approximate Line Number** | 375, 711, 1078 |
| **Function** | `_calculate_confidence_delta` |
| **Description** | The `confidence_delta` field measures `abs(logician.confidence - creative.confidence)`. This is the difference in self-reported confidence scores, not semantic diversity of the answers. The field was historically named `diversity_metric` in the original audit and has been renamed to `confidence_delta`, which is now accurate. |
| **Expected Behaviour** | The field name accurately describes what it measures: confidence delta. |
| **Current Behaviour** | Currently correctly named `confidence_delta`. |
| **Impact** | Low. Field is correctly named in current code. Noted for historical reference. |
| **Root Cause** | Previous iteration, now resolved. |
| **Suggested Resolution** | None — already resolved. |
| **Dependencies** | None |
| **Estimated Complexity** | None |
| **Related Issues** | LOW-003 |

---

### LOW-003: Score_a and Score_b Identical in Decision Dict

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Data Integrity |
| **Status** | 🟢 Open |
| **File** | orchestrator/pipelines.py |
| **Approximate Line Number** | 368, 703, 1070 |
| **Function** | `build_decision_dict` (in prompt_utils.py) |
| **Description** | The decision dict sets both `score_a` and `score_b` to `logician_confidence * 10` and `creative_confidence * 10` respectively. These are the agents' self-assessed confidence scores, not evaluation scores from the judge. The judge produces a single `validation_score` applied to the final synthesized answer. This means `score_a` and `score_b` in the decision dict do not reflect how the judge rated each individual agent's output. |
| **Expected Behaviour** | `score_a` should reflect the judge's evaluation of the Logician's answer quality; `score_b` the Creative's. |
| **Current Behaviour** | Both scores reflect agent self-confidence, not judge evaluation. Since the `aetherisOutput` schema does not expose per-agent scores, both values are derived from the agents' own confidence. |
| **Impact** | Low. The frontend could display misleading per-agent quality scores. |
| **Root Cause** | The `aetherisOutput` schema and judge prompt do not request separate scores for each agent. |
| **Suggested Resolution** | Enhance the judge prompt to request separate scores for Logician and Creative outputs, then populate `score_a` and `score_b` from those values. |
| **Dependencies** | core/schemas.py, orchestrator/evaluation.py |
| **Estimated Complexity** | Low (1-2 days) |
| **Related Issues** | LOW-002 |

---

### LOW-004: Private Method _get_state Accessed Externally

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Encapsulation |
| **Status** | 🟢 Open |
| **File** | api_gateway/rate_limiter.py |
| **Approximate Line Number** | 906-908 |
| **Class** | AsyncAPIGateway |
| **Function** | `execute_with_fallback` |
| **Description** | Same as HIGH-004, but lower severity assessment. The private method `ProviderPool._get_state()` is accessed from `AsyncAPIGateway.execute_with_fallback()`. While this is a layering violation, the practical risk is low because both classes are in the same module. |
| **Expected Behaviour** | Private methods should not be accessed externally. |
| **Current Behaviour** | `pool._get_state(provider_name)` is called at line 907. Public equivalent `pool.get_status(provider_name)` exists. |
| **Impact** | Low. Both classes are co-located in the same module file. Refactoring is unlikely to break this accidentally. |
| **Root Cause** | Developer oversight. |
| **Suggested Resolution** | Replace with `pool.get_status(provider_name)` and access error count from the returned dict. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (30 minutes) |
| **Related Issues** | HIGH-004 |

---

### LOW-005: Stale __pycache__ Artifacts

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Data Integrity |
| **Status** | 🟢 Open |
| **File** | api_gateway/__pycache__/provider_pool.cpython-313.pyc, orchestrator/__pycache__/judges.cpython-313.pyc |
| **Approximate Line Number** | — |
| **Class** | — |
| **Function** | — |
| **Description** | Compiled bytecode files exist for source modules that have been deleted: `provider_pool.py` and `judges.py`. While Python does not normally load orphaned `.pyc` files, they can cause confusion during debugging or if `importlib` is used to force-load them. |
| **Expected Behaviour** | `__pycache__` should only contain bytecode for existing source modules. |
| **Current Behaviour** | Two orphaned `.pyc` files from deleted modules remain. |
| **Impact** | Low. Unlikely to affect normal operation. |
| **Root Cause** | Source modules were deleted but bytecode cache was not cleared. |
| **Suggested Resolution** | Delete the orphaned `.pyc` files. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (5 minutes) |
| **Related Issues** | — |

---

### LOW-006: Documentation References Old Folder Structure

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Documentation |
| **Status** | 🟢 Open |
| **File** | README.md |
| **Approximate Line Number** | 211-213 |
| **Class** | — |
| **Function** | — |
| **Description** | The README project structure (lines 178-213) references a `web/` directory containing `index.html`. The actual frontend is now in `aetheris-ui/` with a full Vite build pipeline. The old `web/` directory no longer exists. |
| **Expected Behaviour** | Documentation should reflect the current project structure. |
| **Current Behaviour** | README shows `web/ └── index.html` as the frontend structure. |
| **Impact** | Low. Developers following the README structure may be confused about where frontend code lives. |
| **Root Cause** | Documentation was not updated after frontend restructuring. |
| **Suggested Resolution** | Update README to reference `aetheris-ui/` structure instead of `web/`. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (30 minutes) |
| **Related Issues** | — |

---

### LOW-007: No Validation on State Machine Hook Registration

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Code Quality |
| **Status** | 🟢 Open |
| **File** | orchestrator/state_machine.py |
| **Approximate Line Number** | 176-199 |
| **Class** | StateMachine |
| **Function** | `register_hook` |
| **Description** | `register_hook` accepts an arbitrary `callable` without any validation. The callback could be any Python callable including lambdas, partials, or any object implementing `__call__`. No type checking, signature validation, or error checking is performed on the callback. |
| **Expected Behaviour** | Hook callbacks should be validated at registration time (e.g., accept no required parameters, or accept specific parameters). |
| **Current Behaviour** | Any callable is accepted without validation. Runtime errors will surface when the hook is executed, not when it is registered. |
| **Impact** | Low. Currently no external code registers hooks, so this is theoretical. |
| **Root Cause** | Implementation focused on functionality over defensive programming. |
| **Suggested Resolution** | Add a `callable` type check and optionally validate that the callable accepts zero arguments (since hooks are called with no arguments). |
| **Dependencies** | None |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | — |

---

### LOW-008: Hardcoded Frontend Constants

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | Configuration |
| **Status** | 🟢 Open |
| **File** | aetheris-ui/src/App.jsx, aetheris-ui/src/api/client.js |
| **Approximate Line Number** | App.jsx:21, client.js:9 |
| **Class** | — |
| **Function** | — |
| **Description** | The frontend has several hardcoded constants: `HEALTH_POLL_INTERVAL = 30000` (30 seconds for provider health polling), `apiClient` timeout = `900000` (15 minutes), and API base URL falls back to `http://localhost:8000`. These values cannot be configured without modifying source code. |
| **Expected Behaviour** | Configuration values should use environment variables or a config file. |
| **Current Behaviour** | Values are hardcoded with no override mechanism (except `VITE_API_BASE_URL` which uses a `.env.example`). |
| **Impact** | Low. Only affects deployment flexibility. |
| **Root Cause** | Development convenience. |
| **Suggested Resolution** | Use Vite environment variables for all configurable constants: `import.meta.env.VITE_HEALTH_POLL_INTERVAL`, `import.meta.env.VITE_API_TIMEOUT`. |
| **Dependencies** | None |
| **Estimated Complexity** | Low (1 hour) |
| **Related Issues** | — |
