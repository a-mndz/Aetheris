# AETHERIS Backend Audit — Deep Component Inspection

**Audit Date:** 2026-06-27
**Auditor:** Principal Backend Engineer
**Scope:** Complete static analysis of every backend component, execution flow, resource management, concurrency, error handling, and observability.

---

## Table of Contents

1. [Component Inventory](#1-component-inventory)
2. [Pipeline Analysis](#2-pipeline-analysis)
3. [Conversation Director](#3-conversation-director)
4. [Prompt Manager](#4-prompt-manager)
5. [Runtime Engine](#5-runtime-engine)
6. [Scheduler](#6-scheduler)
7. [Execution Passport](#7-execution-passport)
8. [State Machine](#8-state-machine)
9. [Reasoning Graph](#9-reasoning-graph)
10. [Provider Registry & Strategy](#10-provider-registry--strategy)
11. [Provider Adapters](#11-provider-adapters)
12. [Streaming Manager](#12-streaming-manager)
13. [Checkpoint Manager](#13-checkpoint-manager)
14. [Memory Manager](#14-memory-manager)
15. [Decision Engine](#15-decision-engine)
16. [Security Validator](#16-security-validator)
17. [JSON Schemas & Pydantic Models](#17-json-schemas--pydantic-models)
18. [Prompt Loading & XML Contracts](#18-prompt-loading--xml-contracts)
19. [Error Handling & Retries](#19-error-handling--retries)
20. [Resource & Memory Leaks](#20-resource--memory-leaks)
21. [Token & Context Waste](#21-token--context-waste)
22. [Provider Routing](#22-provider-routing)
23. [Streaming & Async Safety](#23-streaming--async-safety)
24. [Race Conditions & Exception Handling](#24-race-conditions--exception-handling)
25. [Logging & Observability](#25-logging--observability)

---

## 1. Component Inventory

| # | Component | File | Lines | Status | Assessment |
|---|-----------|------|-------|--------|------------|
| 1 | Pipeline (Micro-Mode) | `orchestrator/pipelines.py` | 1152 | Active | ⚠️ Dual paths, monolithic |
| 2 | Conversation Director | `orchestrator/conversation.py` | 452 | Active | ⚠️ In-memory only |
| 3 | Prompt Manager | `agents/prompt_manager.py` | 338 | Active | ✅ Good |
| 4 | Runtime Engine | `core/runtime.py` | 614 | Active (but unused) | 🔴 Dead code path |
| 5 | Pipeline Scheduler | `orchestrator/pipeline_scheduler.py` | 679 | Dead | 🔴 Never imported |
| 6 | Execution Passport | `core/passport.py` | 339 | Active | ✅ Good |
| 7 | State Machine | `orchestrator/state_machine.py` | 259 | Active | ✅ Good |
| 8 | Reasoning Graph | `orchestrator/reasoning_graph.py` | 308 | Active | ⚠️ Placeholder embeddings |
| 9 | Provider Strategy | `api_gateway/strategy.py` | — | Active | ⚠️ Hardcoded maps |
| 10 | Provider Client | `api_gateway/client.py` | 173 | Active | ⚠️ if/elif routing |
| 11 | Streaming Manager | `orchestrator/streaming.py` | 343 | Active | ⚠️ Duplicate emit methods |
| 12 | Checkpoint Manager | `orchestrator/checkpoints.py` | 370 | Active | 🔴 Memory-only backends |
| 13 | Memory Manager | `orchestrator/memory_manager.py` | 262 | Active | ✅ Good |
| 14 | Decision Engine | `orchestrator/decisions.py` | 516 | Active | ⚠️ Fire-and-forget tasks |
| 15 | Security Validator | `core/security.py` | 367 | Active | ✅ Good |
| 16 | JSON Schemas | `core/schemas.py` | 294 | Active | ⚠️ Duplicate mapping |
| 17 | Claim Manager | `orchestrator/claims.py` | 307 | Active | ⚠️ Placeholder validation |
| 18 | Error Handlers | `core/error_handlers.py` | 459 | Active | ✅ Good |
| 19 | Validators | `core/validators.py` | 500 | Active | ✅ Good |
| 20 | Telemetry Observer | `telemetry/observer.py` | 61 | Active | ⚠️ Global singleton |
| 21 | Background Tasks | `orchestrator/background_tasks.py` | 201 | Active | ✅ Good |
| 22 | Aetheris Orchestrator | `orchestrator/aetheris_orchestrator.py` | 159 | Active | ✅ Factory wiring |
| 23 | Orbiter | `orchestrator/memory.py` | 68 | Active | ⚠️ Global singleton |

---

## 2. Pipeline Analysis

### File: `orchestrator/pipelines.py` (1152 lines)

**Structure:**

| Function | Lines | Purpose | Status |
|----------|-------|---------|--------|
| `run_micro_mode` | 72-444 | Main non-streaming pipeline | Active (legacy) |
| `stream_micro_mode` | 447-724 | Streaming variant | Active (legacy) |
| `_build_frontend_payload` | 726-761 | Result formatting | Active (imported as private) |
| `_ensure_agent_output` | 766-784 | Parse fallback helper | Active |
| `_calculate_confidence_delta` | 787-793 | Confidence diff | Active |
| `_run_with_decision_engine` | 798-1148 | DecisionEngine path | Active (new) |

### Dual Execution Paths (CRIT-001)

`run_micro_mode` forks at line 106:
```python
if decision_engine is not None:
    return await _run_with_decision_engine(...)
# else: ~350 lines of legacy inline path
```

Both paths produce `MicroModeResult` but diverge significantly:

| Aspect | Legacy Path (lines 122-444) | DecisionEngine Path (lines 798-1148) |
|--------|---------------------------|-------------------------------------|
| Breaker gate | Inline with `gateway.execute_with_fallback` | Delegates to `decision_engine.execute_breaker_gate` |
| Parallel generation | `asyncio.gather` with `return_exceptions=True` | Delegates to `decision_engine.execute_generation_agents` |
| Error transitions | 7 identical `try/except ConversationState.FAILED` blocks | 3 similar blocks |
| Claim extraction | Lines 378-427 (49 lines) | Lines 1080-1130 (50 lines, near-identical) |
| Result assembly | Lines 434-444 | Lines 1137-1147 |

### Execution Order Verification

The pipeline executes in this order:

1. **Conversation context init** — `init_conversation_context` (line 97 or 822)
2. **Breaker gate** — DecisionEngine or inline (100ms timeout)
3. **Parallel generation** — Logician + Creative (30s timeout)
4. **Judge synthesis** — `arbitrate_and_synthesize`
5. **Claim extraction** — From all 4 agent outputs
6. **Result assembly** — `build_decision_dict` + output

### Conversation State Transition Duplication

The pattern `if conversation_director and session_id: try: from orchestrator.conversation import ConversationState; ...` appears **7 times** in the legacy path and **3 times** in the DecisionEngine path. A helper `transition_conversation_to_failed` exists in `core/error_handlers.py:223` but is never used by either path.

---

## 3. Conversation Director

### File: `orchestrator/conversation.py` (452 lines)

**Assessment: Functionally complete but non-persistent.**

| Feature | Status | Details |
|---------|--------|---------|
| Session creation | ✅ | UUID-based, validations |
| State transitions | ✅ | 4 states with transition map |
| History truncation | ✅ | 80% threshold, 5 preserved turns |
| Expiration | ⚠️ | Implemented but sessions are in-memory |
| Persistence | 🔴 | `self._sessions: dict[str, ConversationSession]` — lost on restart |

### State Machine Validation

```python
VALID_CONVERSATION_TRANSITIONS = {
    ACTIVE: [WAITING, COMPLETED, FAILED],
    WAITING: [ACTIVE, COMPLETED, FAILED],
    COMPLETED: [],
    FAILED: [],
}
```

Issue: No transition from ACTIVE or WAITING to another ACTIVE state (for continuing an active conversation).

### Truncation Accuracy

The `truncate_history` method (line 311) separates system prompts and preserves the `PRESERVED_TURNS` most recent non-system turns. However, the summary generation (line 364) uses a rough character-count estimator (`len(part) // 4`), not actual token counting.

### Expiry Cleanup

`cleanup_expired_sessions` (line 388) is a non-async method called from an async background task via `periodic_cleanup_task` with `is_async=False`. The method iterates `self._sessions` which may be modified concurrently by pipeline code — no lock is held.

---

## 4. Prompt Manager

### File: `agents/prompt_manager.py` (338 lines)

**Assessment: Solid implementation with proper validation.**

| Function | Purpose | Assessment |
|----------|---------|------------|
| `clean_xml_prompt` | Strip markdown fences from XML | ✅ Handles ```xml and ``` |
| `validate_xml` | ElementTree XML parsing | ✅ Catches malformed XML |
| `load_prompt_file` | Read file with error handling | ✅ 4 error types handled |
| `load_runtime_contracts` | Load 00-11 XML files sorted | ✅ Directory existence check |
| `load_system_prompt` | Load with fallback to persona constants | ✅ Graceful degradation |
| `get_load_order_verification` | Verify hierarchy | ✅ Full validation report |
| `assemble_agent_prompt` | Assemble ROLE + contracts + prompt | ✅ Hierarchical assembly |

### Prompt Loading Hierarchy

```
1. <ROLE> block (role, stage, objective, iteration, execution_mode)
2. Runtime contracts 00-11 (sorted by prefix)
   - 00_agent_runtime.xml
   - 01_prompt_loader.xml
   - 02_response_contract.xml
   - 03_context_manager.xml
   - 04_execution_contract.xml
   - 05_error_handling.xml
   - 06_pipeline_state.xml
   - 07_memory_manager.xml
   - 08_stream_contract.xml
   - 09_provider_contract.xml
   - 10_security_contract.xml
   - 11_completion_contract.xml
3. Agent-specific system prompt (e.g., 05_logician.xml)
```

### Issue: Redundant Loading

Every `assemble_agent_prompt` call reloads all 12 runtime contracts from disk via `load_runtime_contracts` (line 330). No caching mechanism exists. With 3+ agents per pipeline execution (Breaker, Logician, Creative, Judge), this results in 48+ file read + XML validation operations per request.

---

## 5. Runtime Engine

### File: `core/runtime.py` (614 lines)

**Assessment: Well-designed but completely unused by pipeline code.**

### The 270-Line Dead Code Path

`RuntimeEngine.execute_with_contracts` (lines 236-506) is the intended contract enforcement layer. It performs:

1. Security validation (line 281)
2. Rate limiting via ResourceManager (line 329)
3. AGENT_STARTED streaming event (line 363)
4. `gateway.execute_with_fallback` call (line 381)
5. AGENT_COMPLETED streaming event (line 408)
6. Timeout enforcement (line 381)
7. Metrics tracking (line 397)
8. Resource release in `finally` (line 503)

None of this code is executed. Pipeline code calls `gateway.execute_with_fallback()` directly.

### Why It's Bypassed

The `execute_with_contracts` method signature (line 236-248) accepts overlapping parameters with `execute_with_fallback` but adds `passport`, `contract_name`, and `user_id`. The pipeline would need to wrap every gateway call through this method. The `aetheris_orchestrator.py` instantiates `RuntimeEngine` (line 98) but never passes it to `pipelines.py`.

### Duplicate Streaming Event Emission

Lines 290-325, 340-353, 363-376, 408-423, 447-461, 483-497 contain 6+ near-identical blocks that:
1. Import `EventType` and `StreamEvent` from `orchestrator.streaming` inside method body
2. Create `asyncio.create_task(self.streaming_manager.emit_event(...))`
3. Construct `StreamEvent` with timestamp

### Import Pattern Problem

```python
from orchestrator.streaming import EventType, StreamEvent
```
This import at line 291 and others inside method bodies creates a **back-edge from core layer to orchestrator layer**, violating the dependency hierarchy.

---

## 6. Scheduler (Dead Code)

### File: `orchestrator/pipeline_scheduler.py` (679 lines)

**Assessment: Complete module, never imported, never used.**

| Function | Lines | Purpose |
|----------|-------|---------|
| `PipelineScheduler` class | 64-679 | Full pipeline orchestration |
| `execute_pipeline` | 105-221 | Complete 6-stage pipeline |
| `execute_stage` | 223-325 | Single stage with state machine + checkpoint |
| `execute_parallel_agents` | 327-445 | Gather with return_exceptions |
| `handle_stage_failure` | 447-530 | Failure recovery with fallback |
| `emit_stage_transition` | 532-580 | Streaming telemetry |
| `update_state_machine` | 582-620 | State machine transitions |

This module is more comprehensive than the inline pipeline path. It integrates:
- State machine transitions for every stage
- Checkpoint creation after each major stage
- Streaming event emission for stage transitions
- Fallback chain on agent failure

It was never wired into `orchestrator/__init__.py` or any entry point.

---

## 7. Execution Passport

### File: `core/passport.py` (339 lines)

**Assessment: Excellent implementation — thread-safe, well-validated.**

| Feature | Status | Details |
|---------|--------|---------|
| Thread safety | ✅ | `threading.Lock` on all mutation methods |
| UUID v4 validation | ✅ | `__post_init__` validates UUID version |
| Execution timeout | ✅ | 300s default, `enforce_timeout` method |
| Agent output cap | ✅ | 10-max agent outputs |
| Error/warning caps | ✅ | 100-max entries with FIFO |
| Immutable request_id | ✅ | `__setattr__` guard |
| Logging retry | ✅ | 3 attempts with 1s delay |
| Deep copy safety | ✅ | `snapshot()` uses `deepcopy` |

### Issues

1. **Duplicate datetime utilities** (line 36-43): `_as_utc` and `_iso_utc` wrap `core.validators` functions. These are unnecessary wrappers — callers could import from validators directly.

2. **`_lock` field in dataclass**: The `threading.Lock` is excluded from `__init__` via `init=False`, but dataclass `__hash__` is not implemented, so passports cannot be used as dict keys or set members. This is intentional (mutable state), but could surprise developers.

3. **No async lock**: All mutations use `threading.Lock`, which blocks the event loop thread. For a single-threaded asyncio application this is acceptable, but if passport is ever shared across threads, `threading.Lock` is correct.

4. **`check_timeout` alias** (line 270): The `enforce_timeout` method has an alias `check_timeout` that does the same thing. This is dead API surface.

---

## 8. State Machine

### File: `orchestrator/state_machine.py` (259 lines)

**Assessment: Clean, well-structured, proper.**

| Feature | Status | Details |
|---------|--------|---------|
| 10 pipeline states | ✅ | IDLE → NORMALIZING → BREACH_CHECKING → GENERATING → EVALUATING → SYNTHESIZING → FORMATTING → COMPLETED |
| 3 terminal states | ✅ | COMPLETED, FAILED, ABORTED |
| Transition validation | ✅ | Explicit transition map |
| Hook system | ✅ | on_enter, on_exit, on_transition |
| Rollback on hook failure | ✅ | Reverts to previous state |
| History tracking | ✅ | 100 transitions max via deque |

### Transition Map

```
IDLE → NORMALIZING
NORMALIZING → BREACH_CHECKING | FAILED
BREACH_CHECKING → GENERATING | ABORTED | FAILED
GENERATING → EVALUATING | FAILED
EVALUATING → SYNTHESIZING | FAILED
SYNTHESIZING → FORMATTING | FAILED
FORMATTING → COMPLETED | FAILED
COMPLETED → (terminal)
FAILED → (terminal)
ABORTED → (terminal)
```

### Issue: Hook Validation (LOW-007)

`register_hook` (line 175) accepts any `Callable` without signature validation. If a hook expects parameters, it will fail at runtime with a confusing error. Suggested fix: accept only `Callable[[], None]` (zero-argument callbacks).

### Issue: Not Integrated

The StateMachine is created by `create_request_state_machine` in `aetheris_orchestrator.py` but is never actually used. No pipeline code references `StateMachine`. The `VALID_TRANSITIONS` map and state management are unused.

---

## 9. Reasoning Graph

### File: `orchestrator/reasoning_graph.py` (308 lines)

**Assessment: Graph structure is sound; embeddings are placeholder.**

| Feature | Status | Details |
|---------|--------|---------|
| Node/Edge graph | ✅ | Adjacency list with reverse edges |
| Node types | ✅ | CLAIM, QUERY, REASONING_STEP |
| Edge types | ✅ | SUPPORTS, CONTRADICTS, REFINES, FAILS |
| Similarity search | ⚠️ | Character-frequency-based placeholder |
| Failure patterns | ✅ | Case-insensitive substring matching |
| Expiry | ✅ | 30-day TTL with cleanup |

### Placeholder Embeddings (MED-009)

`_placeholder_embedding` (line 199) generates a 26-dimensional vector from character frequency (a-z counts normalized by total). This is **not semantic** — two texts with different meanings but similar letter distributions would be considered similar. For example, "The sky is blue" and "Buy sky blue paint" share significant character frequency overlap.

### Similarity Search Limitation

`find_similar_nodes` (line 234) computes cosine similarity on placeholder embeddings. This means:
- `"quantum physics"` and `"quantum mechanics"` — character frequency differs (no 'c' in 'physics', etc.)
- `"What is the capital of France?"` and `"France capital city"` — both have similar letter distributions, so this happens to work
- `"Python programming"` and `"Snake handling"` — both contain 'p', 'y', 't', 'h', 'o', 'n' but are semantically unrelated

### Failure Pattern Matching

`get_failure_patterns` (line 167) uses case-insensitive substring matching on queries. This means:
- Exact match → ✅ found
- "capital of France" → substring of "What is the capital of France?" → ✅ found
- "Paris capital" → no match for "capital of France" → ❌ not found

---

## 10. Provider Registry & Strategy

### File: `api_gateway/strategy.py`

**Assessment: Hardcoded model maps, no extensibility.**

| Feature | Status | Details |
|---------|--------|---------|
| FREE_MODELS | ⚠️ | Hardcoded dict of role→[model list] |
| HYBRID_MODELS | ⚠️ | Hardcoded dict |
| PAID_MODELS | ⚠️ | Hardcoded dict |
| ProviderStrategy | ✅ | Selects model chain based on mode |

### Open/Closed Violation (SOLID)

Adding a new model or provider requires modifying the `FREE_MODELS`, `HYBRID_MODELS`, or `PAID_MODELS` dictionaries. There is no provider registry or plugin mechanism. The strategy maps should be configurable via environment variables or a configuration file.

### Model Chain Example

For HYBRID mode, the model chain for "breaker" role might be:
```python
["openrouter/anthropic/claude-sonnet-4.6", "openrouter/openai/gpt-4o-mini", "openrouter/meta-llama/llama-3.1-8b-instruct"]
```

This means all 3 models are tried in sequence if the first fails (fallback chain).

---

## 11. Provider Adapters

### File: `api_gateway/client.py` (173 lines)

**Assessment: Working but rigid provider routing.**

### The if/elif Chain (lines 61-91)

```python
if provider == "openrouter": url = "..."; headers = {...}
elif provider == "groq": url = "..."; headers = {...}
elif provider in {"nvidia", "nvidia-nim"}: ...
elif provider == "github": ...
elif provider == "mistral": ...
elif provider == "google": ...
elif provider == "openai": ...
elif provider == "kie": ...
elif provider in {"unli", "unli-dev"}: ...
elif provider == "local": ...
else: raise ValueError(f"Unsupported provider prefix: {provider}")
```

**Issues:**
1. Adding a new provider requires a new `elif` branch
2. URLs and auth patterns are hardcoded — cannot be configured
3. The `local` provider URL (`http://localhost:11434`) is hardcoded

### Instruction Reinforcement (lines 47-49)

Every API call appends:
```python
{"role": "system", "content": "CRITICAL REMINDER: ..."}
```

This adds approximately 80-120 tokens per LLM call. With 3-4 calls per pipeline request (Breaker, Logician, Creative, Judge), this wastes 240-480 tokens per request.

### Response Format

```python
if provider not in {"nvidia", "nvidia-nim"}:
    payload["response_format"] = {"type": "json_object"}
```

NVIDIA NIM does not support `response_format`, so it is excluded. However, `simulation` and `local` providers are also included in the condition (they don't set json_object either, but they bypass this code path).

### Telemetry I/O Logging (lines 107-124)

Model I/O is logged to a flat file (`logs/model_io.log`):
- No log rotation
- No size limits
- No sanitization of sensitive data in log output

### Simulation Mode Provider Check (lines 127-148)

`_is_simulated` has a 9-branch if/elif chain that mirrors the URL routing. If a provider's API key is empty, it falls back to simulation. This means an empty API key string silently returns deterministic mock responses instead of raising an error.

---

## 12. Streaming Manager

### File: `orchestrator/streaming.py` (343 lines)

**Assessment: Functional but with concurrency and datetime issues.**

| Feature | Status | Details |
|---------|--------|---------|
| Stream lifecycle | ✅ | create/close/iterate |
| Payload limits | ✅ | 64KB with truncation |
| Buffer management | ✅ | 1000 events per stream |
| Stale cleanup | ✅ | 300s timeout |
| Event types | ✅ | 18 EventType values |

### Naive Datetime (HIGH-010)

```python
timestamp: datetime = field(default_factory=datetime.utcnow)  # line 64
```

`datetime.utcnow()` returns a naive datetime (no timezone info). All other datetime fields in the codebase use timezone-aware UTC. This causes `to_dict()` to produce `2026-06-27T12:00:00` instead of `2026-06-27T12:00:00+00:00`.

### Duplicate Emit Methods (MED-005)

Three methods for emitting events:
1. `emit_event` (line 168) — takes `StreamEvent` object
2. `emit` (line 302) — takes `EventType` + `dict`, wraps in `StreamEvent`
3. `emit_raw` (line 318) — takes raw `dict`, parses event type

The `emit_raw` method has a side effect: it calls `event_dict.pop("event", "progress")` which **mutates the caller's dict** (line 333). This could cause subtle bugs if the caller reuses the dict.

### No Synchronization (ASY-003)

`_active_streams`, `_stream_timestamps`, and `_stream_tasks` are all regular dicts accessed from multiple tasks without any synchronization primitive. While asyncio is single-threaded, concurrent tasks can interleave at `await` points, making these accesses technically safe but fragile.

### Backpressure

The `emit_event` method (line 168) drops the oldest event when the buffer is full (line 221-224: `queue.get_nowait()`). This means events are silently dropped with no indication to the frontend.

---

## 13. Checkpoint Manager

### File: `orchestrator/checkpoints.py` (370 lines)

**Assessment: Well-designed API; storage backends incomplete.**

| Backend | Lines | Status |
|---------|-------|--------|
| `memory` | 241-255 | ✅ Implemented |
| `filesystem` | 257-259 | 🔴 `raise NotImplementedError` |
| `database` | 271-273, 294-296, 319-321 | 🔴 `raise NotImplementedError` |

### Impact (CRIT-003)

Checkpoints are in-memory only. They are lost on:
- Server restart
- Process crash
- Deployment

Since checkpoints were designed for pipeline recovery after failures, the memory-only backend defeats their purpose.

### Size Enforcement

Size limits are enforced before serialization:
- `MAX_CHECKPOINT_SIZE_MB = 10` (line 67)
- `MAX_AGENT_OUTPUT_SIZE_MB = 5` (line 68)

The size estimation (`_estimate_checkpoint_size`, line 355) serializes to JSON and measures bytes. For very large outputs, this serialization itself could be expensive.

### Expiry

`_expire_checkpoints_impl` (line 298) removes expired checkpoints based on `expires_at`. The `expire_checkpoints` async wrapper (line 210) handles timeouts gracefully via `with_timeout`.

---

## 14. Memory Manager

### File: `orchestrator/memory_manager.py` (262 lines)

**Assessment: Well-structured with multiple compression strategies.**

| Strategy | Lines | Description |
|----------|-------|-------------|
| TRUNCATION | 185-201 | Keep system prompts + last N turns |
| SEMANTIC_COMPRESSION | 203-225 | Summary of removed turns (max 500 tokens) |
| HIERARCHICAL | 227-252 | Multi-level summaries (max 300 tokens/level) |

### Token Counting

Uses `tiktoken` when available (line 79-83):
```python
try:
    import tiktoken
    self._token_encoder = tiktoken.get_encoding("cl100k_base")
except ImportError:
    # Falls back to word-count heuristic (~1.3 tokens/word)
```

The fallback is a rough estimate and may over or under-count depending on language.

### Compression Rejection

`should_compress` triggers at 80% of context limit (TRUNCATION_THRESHOLD = 0.8). The `InsufficientCapacityError` (line 27) is raised if compression cannot reduce below 90% (COMPRESSION_REJECTION_THRESHOLD = 0.9). However, the `compress_history` method **catches this exception** and returns the truncated result anyway (line 140-146).

### Issue: Not Integrated with Pipeline

The MemoryManager is created in `aetheris_orchestrator.py` but never referenced by any pipeline code. The pipeline uses `ConversationDirector` for history management and `EpistemicMemory` for failure tracking, but not `MemoryManager`.

---

## 15. Decision Engine

### File: `orchestrator/decisions.py` (516 lines)

**Assessment: Sound architecture with timing specifications; fire-and-forget tasks.**

| Feature | Status | Details |
|---------|--------|---------|
| Breaker gate (100ms) | ✅ | `asyncio.wait_for` with 100ms timeout |
| Parallel generation (30s) | ✅ | `asyncio.wait_for` with 30s timeout |
| Judge synthesis | ✅ | Delegates to `arbitrate_and_synthesize` |
| Rolling metrics | ✅ | 100-window deques |
| Three strategies | ✅ | PARALLEL, SEQUENTIAL, CONDITIONAL |

### Fire-and-Forget Tasks (MED-012)

`asyncio.create_task` is used at 4+ locations without error handling:

| Location | Line | Event |
|----------|------|-------|
| execute_breaker_gate | 161 | BREAKER_FAILED |
| execute_breaker_gate | 175 | BREAKER_PASSED |
| execute_generation_agents | 213 | GENERATION_COMPLETED |
| execute_judge_synthesis | 289 | JUDGE_SYNTHESIZED |

None of these tasks are:
- Stored for later awaiting
- Given error callbacks via `add_done_callback`
- Cancelled on pipeline abort

If the streaming manager's `emit_event` raises (e.g., queue full), the exception is silently lost.

### Breaker Gate Implementation

```python
async def execute_breaker_gate(self, query, gateway, strategy, pool, passport, history):
    try:
        breaker_output = await asyncio.wait_for(
            self._execute_breaker(...), timeout=self.BREAKER_TIMEOUT_MS / 1000.0
        )
    except asyncio.TimeoutError:
        return False, None  # No output on timeout
    except Exception as exc:
        return False, None  # No output on error
```

The Breaker gate returns `(False, None)` on timeout or error, meaning the pipeline **cannot distinguish between "knowledge absence detected" and "Breaker timed out"**. Both result in an abort with no output.

### Conditional Strategy

The CONDITIONAL strategy (line 474) runs Logician first, then Creative only if Logician's confidence < 0.7. If Logician confidence >= 0.7, `creative_output` is set to `None`. This means conditional mode never provides a second opinion when Logician appears confident, which could miss cases where a confident Logician is confidently wrong.

---

## 16. Security Validator

### File: `core/security.py` (367 lines)

**Assessment: Robust implementation with comprehensive injection detection.**

| Feature | Status | Details |
|---------|--------|---------|
| Injection patterns | ✅ | 10 regex patterns |
| Secret detection | ✅ | 5 regex patterns for API keys, passwords, tokens |
| Unicode validation | ✅ | Validates Unicode categories (L, N, P, S, Z) |
| Input length limit | ✅ | 10,000 characters |
| JWT auth | ✅ | OAuth2 with bcrypt passwords |
| Thread-safe metrics | ✅ | `threading.Lock` on counters |

### Injection Patterns (lines 82-93)

Ten patterns covering common prompt injection vectors:
- "ignore previous instructions"
- "disregard all prior instructions"
- "new instructions:"
- "you are now"
- "system:", "assistant:"
- "system override/prompt/instruction"
- "forget everything/previous"
- HTML-like tags `<system>`, `<instruction>`
- JSON-like `{"system": ...}`, `{"role": "system"}`

### Duplicate SecurityValidationError (HIGH-002)

`core/security.py:51` defines `SecurityValidationError(ValueError)`. `core/error_handlers.py:38` defines `SecurityValidationError(AETHERISException)`. These are different types. The `error_handlers.py` version is never imported.

### `validate_or_raise` (line 209)

```python
def validate_or_raise(self, user_input: str) -> str:
    is_valid, violations = self.validate_input(user_input)
    if not is_valid:
        raise SecurityValidationError(violations)
    return user_input
```

This method never actually scrubs the input — it only validates. The name suggests it might both validate and raise. Unlike `scrub_secrets` (line 243), this method does not clean the input.

### `separate_system_user_prompts` (line 278)

Builds distinct messages for system and user content:
```python
messages = []
if system_prompt:
    messages.append({"role": "system", "content": system_prompt})
messages.append({"role": "user", "content": self.escape_user_input(user_input)})
```

This is the recommended pattern for injection prevention — user input is JSON-escaped and placed in a separate message. However, this method is **never called** by pipeline code. The pipeline appends system prompt and user prompt as separate strings to `gateway.execute_with_fallback`, which reconstructs them as messages inside `post_request`.

---

## 17. JSON Schemas & Pydantic Models

### File: `core/schemas.py` (294 lines)

**Assessment: Well-designed schemas with duplicate field mapping.**

| Model | Lines | Purpose | Status |
|-------|-------|---------|--------|
| SignalState | 21-56 | Real-time evaluation metrics | 🟡 Unused (Phase 2) |
| AgentOutput | 62-165 | Structured agent output | ✅ Active |
| aetherisOutput | 170-235 | Final synthesis output | ✅ Active |
| SessionMetadata | 241-253 | Session metadata | ✅ Active |
| PipelineResult | 255-268 | Complete pipeline result | ✅ Active |
| ProviderHealthStatus | 271-282 | Provider health snapshot | ✅ Active |
| CheckpointData | 284-294 | Checkpoint resume state | ✅ Active |

### Duplicate Field Mapping (MED-010)

Both `AgentOutput.map_contract_fields` (line 75) and `aetherisOutput.map_contract_fields` (line 177) implement near-identical field resolution logic:

- Alternative field names for `answer`: `summary`, `draft_answer`, `primary_solution`, etc.
- Alternative field names for `reasoning_steps`: `claims`, `logical_analysis`, `progress`, etc.
- Confidence label-to-float conversion: `{"high": 0.9, "medium": 0.5, "low": 0.2}`

A shared utility `resolve_field` exists in `core/validators.py:467` but is not used by either schema.

### Confidence Ambiguity

`AgentOutput.confidence` is a `float` (0.0-1.0), while `aetherisOutput.overall_confidence` is a `str` ("High"/"Medium"/"Low"). The `build_decision_dict` function in `prompt_utils.py` converts float to score by multiplying by 10, then the frontend payload builder (`_build_frontend_payload`) divides by 10 again — a round-trip conversion that loses precision.

---

## 18. Prompt Loading & XML Contracts

### File: `agents/prompt_manager.py` + `prompts/runtime/*.xml` + `prompts/system/*.xml`

**Assessment: Well-organized hierarchy with validation.**

### XML File Inventory

**Runtime Contracts (12 files):**
| File | Purpose |
|------|---------|
| `00_agent_runtime.xml` | Base runtime contract |
| `01_prompt_loader.xml` | Prompt loading instructions |
| `02_response_contract.xml` | Response format contract |
| `03_context_manager.xml` | Context management rules |
| `04_execution_contract.xml` | Execution constraints |
| `05_error_handling.xml` | Error handling rules |
| `06_pipeline_state.xml` | Pipeline state machine |
| `07_memory_manager.xml` | Memory management contract |
| `08_stream_contract.xml` | Streaming contract |
| `09_provider_contract.xml` | Provider API contract |
| `10_security_contract.xml` | Security contract |
| `11_completion_contract.xml` | Completion contract |

**System Personas (13 files):**
| File | Purpose |
|------|---------|
| `01_prompt_normalizer.xml` | Normalizer agent |
| `02_parameter_engine.xml` | Parameter Engine |
| `03_conversation_director.xml` | Conversation Director |
| `04_breaker.xml` | Breaker agent |
| `05_logician.xml` | Logician agent |
| `06_creative.xml` | Creative agent |
| `07_judge_logic.xml` | Logic Judge |
| `08_judge_factual.xml` | Factual Judge |
| `09_synthesizer.xml` | Synthesizer |
| `10_reasoning_budget.xml` | Reasoning Budget |
| `11_streaming.xml` | Streaming contract |
| `12_output_formatter.xml` | Output Formatter |
| `13_json_schema.xml` | JSON Schema contract |

### Execution Order

The expected pipeline execution order (from system prompt filenames):

```
01_prompt_normalizer.xml          → Prompt Normalizer
02_parameter_engine.xml           → Parameter Engine
03_conversation_director.xml      → Conversation Director
04_breaker.xml                    → Breaker
05_logician.xml                   → Logician
06_creative.xml                   → Creative
07_judge_logic.xml                → Judge Logic
08_judge_factual.xml              → Judge Factual
09_synthesizer.xml                → Reasoning Fusion Engine
10_reasoning_budget.xml           → Reasoning Budget
11_streaming.xml                  → Streaming
12_output_formatter.xml           → Output Formatter
13_json_schema.xml                → JSON Schema
```

### Current Pipeline Gap

The Micro-Mode pipeline only uses **4 agent roles**: Breaker, Logician, Creative, and a combined Judge (synthesizer). The following persona prompts are never loaded:
- `01_prompt_normalizer.xml` — No normalizer agent
- `02_parameter_engine.xml` — No parameter engine agent
- `03_conversation_director.xml` — No conversation director prompt
- `07_judge_logic.xml` — No separate logic judge
- `08_judge_factual.xml` — No separate factual judge
- `10_reasoning_budget.xml` — No reasoning budget agent
- `11_streaming.xml` — No streaming-specific prompt
- `12_output_formatter.xml` — No output formatter agent
- `13_json_schema.xml` — No JSON schema enforcement agent

### Prompt Assembly Performance

Each `assemble_agent_prompt` call:
1. Builds ROLE block (string concatenation)
2. Calls `load_runtime_contracts()` — reads and validates 12 XML files
3. Calls `load_system_prompt()` — reads and validates 1 XML file
4. Concatenates all parts

For 3 agent roles (Breaker, Logician, Creative), this is:
- 39 XML files read and validated per pipeline execution
- No caching — repeated reads from disk

### Breaker Never Answers User Prompts ✅

The Breaker persona (line 179 in personas.py) explicitly states:
> "You MUST NOT attempt to answer the query yourself."
> "You are a gate, not a generator."

The Breaker is constrained to return either:
- `"CONTEXT SUFFICIENT — proceed with generation."` (confidence=1.0)
- `"KNOWLEDGE ABSENCE DETECTED — aborting pipeline."` (confidence=0.0)

The pipeline logic (`_is_knowledge_absent` at line 50 of pipelines.py) enforces this by checking for the sentinel and zero confidence.

### Judges Never Generate Answers ✅

The Judge (synthesizer) prompt instructs:
> "You are the Senior Synthesizer Arbiter."
> "Output strictly in raw JSON following the aetherisOutput schema layout."

The judge produces a structured `aetherisOutput` with `final_answer`, `validation_score`, `disagreement_notes` — it evaluates and synthesizes, but does not generate the final user-facing response directly. The pipeline extracts `final_answer` from the judge's output.

### Fusion Produces Final Reasoning ✅

The `arbitrate_and_synthesize` function in `evaluation.py` acts as the Reasoning Fusion Engine. It:
1. Receives both Logician and Creative answers
2. Resolves contradictions logically
3. Produces `final_answer` with `validation_score`
4. Returns `aetherisOutput` with structured reasoning

### Formatter Formats Final Response ✅

`_build_frontend_payload` (pipelines.py:726) transforms the `MicroModeResult` into the frontend-expected shape, including:
- Converting `validation_score` to `confidence_score` (divide by 10)
- Extracting `bias_risk` from decision dict justification string via regex
- Serializing Pydantic models to dicts

---

## 19. Error Handling & Retries

### Error Handling Architecture

| Layer | Mechanism | Coverage |
|-------|-----------|----------|
| Gateway | Retry-with-backoff (3 attempts, base 1.5s) | `_guarded_call` |
| Gateway | Fallback chain (multi-model) | `execute_with_fallback` |
| Gateway | Circuit breaker (5 failures → OPEN, 60s cooldown) | `ProviderPool` |
| Pipeline | Error result return (no exception propagation) | `MicroModeResult(status="error")` |
| Passport | Error recording (100 max) | `record_error` |
| State Machine | Invalid transition exception | `InvalidTransitionError` |
| Streaming | Fire-and-forget (errors silently swallowed) | `asyncio.create_task` |

### Exception Handling Patterns

**Good: Passport exception isolation**
```python
# core/error_handlers.py:112-115
if passport is not None:
    try:
        passport.record_error(stage, error_msg, details)
    except Exception:
        log.warning("Failed to record error in passport")
```

**Bad: Bare except suppression**
```python
# pipelines.py:145-149
if conversation_director is not None and session_id:
    try:
        from orchestrator.conversation import ConversationState
        conversation_director.transition_state(session_id, ConversationState.FAILED)
    except Exception:
        pass  # ← Silently suppresses ALL errors
```

This `try/except/pass` pattern appears 7+ times in pipelines.py. It silently suppresses:
- `ValueError` (invalid session_id)
- `InvalidConversationTransitionError` (invalid state transition)
- `AttributeError` (if conversation_director lacks the method)

### Retry Configuration

| Component | Retries | Backoff | Timeout |
|-----------|---------|---------|---------|
| Gateway `_guarded_call` | 3 | Exponential 1.5^attempt + jitter | None |
| Gateway `execute_with_fallback` | Per-model chain | N/A (models in sequence) | None |
| Passport logging | 3 | 1s fixed | N/A |
| Checkpoint save | Timeout only | N/A | 5s |
| Provider recovery | Exponential | 1.0s → 300.0s (×2) | N/A |

### Missing: Timeout on Gateway Calls

`execute_with_fallback` calls `_guarded_call` which calls `_client.post_request`. There is **no timeout** on the HTTP client call — `httpx.AsyncClient(timeout=600.0)` has a 600-second timeout (client.py:22). This means a single model call can block the pipeline for 10 minutes.

### Missing: Circuit Breaker Integration with Pipeline

The pipeline does not check `ProviderPool.is_provider_available()` before calling `execute_with_fallback`. If all providers in the chain are dead, the pipeline will try each one, wait for timeouts, and eventually raise `AllModelsExhaustedError`.

---

## 20. Resource & Memory Leaks

### RES-001: EpistemicMemory Global Singleton (MEM-001)

`orchestrator/memory.py:67-68`:
```python
epistemic_memory = EpistemicMemory()
```

The global singleton `epistemic_memory` accumulates `failed_loops` up to `max_entries=200`. There is:
- No expiry mechanism
- No persistence
- No way to clear per-request data
- No thread-safety (the deque is not synchronized)

Every pipeline request with `validation_score < 7.0` appends to this deque (pipelines.py:358-362, 1021-1028).

### RES-002: TelemetryObserver Global Singleton

`telemetry/observer.py:60-61`:
```python
observer = TelemetryObserver()
```

The global singleton accumulates tokens and costs indefinitely. There is:
- No reset mechanism (except direct mutation)
- No persistence
- No serialization

### RES-003: ConversationDirector Session Memory

`conversation.py:92`:
```python
self._sessions: dict[str, ConversationSession] = {}
```

Sessions are never persisted to database. All session data is lost on:
- Server restart
- Process crash
- Deployment

### RES-004: HTTP Connection Pool Not Cleaned

`rate_limiter.py:824`:
```python
self._client = client or AsyncHTTPClient()
```

The `AsyncHTTPClient` creates an `httpx.AsyncClient` which maintains a connection pool. While `close()` exists (client.py:172), it is only called from `AsyncAPIGateway.close()` (rate_limiter.py:838-839), which is never called by pipeline code or entry points.

---

## 21. Token & Context Waste

### TOK-001: Instruction Reinforcement (80-120 tokens/call)

`client.py:47-49`:
```python
messages.append({
    "role": "system",
    "content": "CRITICAL REMINDER: ..."
})
```

This ~100-token reminder is appended to every LLM API call, including the synthesizer judge which uses a different output schema (`aetherisOutput` with `final_answer`, not `AgentOutput` with `answer`). The reminder instructs the model to output 3 specific JSON keys, but the judge must output 5 different keys.

### TOK-002: Claim Extraction Overhead

`pipelines.py:377-406` and `1080-1130`:
Claim extraction runs on every pipeline execution, processing all 4 agent outputs. Each claim undergoes regex extraction, classification, and provenance tracking. However, `validate_claim` always returns `UNVERIFIED` with `confidence=0.3`. The extracted claims are never verified.

Estimated overhead: 50-200ms per pipeline execution for no actionable output.

### TOK-003: Duplicate Runtime Contract Loading

`prompt_manager.py:330`:
```python
runtime_prompts = load_runtime_contracts(prompts_dir)
```

This loads all 12 runtime contract XML files on every `assemble_agent_prompt` call. Since each agent prompt is assembled per pipeline execution, the 12 XML files are read and validated 3-4 times per request.

### CTX-001: Full Context Injection for All Agents

The `assemble_agent_prompt` hierarchy (line 276) injects:
1. ROLE block (dynamic, ~50 tokens)
2. All 12 runtime contracts (static, ~2000+ tokens)
3. Agent-specific system prompt (static, ~500+ tokens)

This means every agent (including the Breaker, which is supposed to be "lightweight") receives ~2500 tokens of context. The Breaker prompt explicitly asks for "UNDER 50 WORDS" but receives the same heavy context as the generation agents.

### CTX-002: No Prompt Caching

Runtime contracts (12 XML files) are loaded from disk on every `assemble_agent_prompt` call. They are static files that never change during runtime. A simple `functools.lru_cache` on `load_runtime_contracts` would eliminate repeated disk I/O.

---

## 22. Provider Routing

### PRV-001: String-Based Provider Routing

`client.py:61-91`: 9-branch if/elif chain maps provider name to URL and auth headers. This violates the Open/Closed Principle — adding a new provider requires:
1. Adding URL and auth logic to the if/elif chain
2. Adding API key to config
3. Adding key check in `_is_simulated`

### PRV-002: Fallback Chain Construction

`strategy.py`: Model chains are hardcoded dictionaries. The `execute_with_fallback` method (rate_limiter.py:841) iterates the chain sequentially:
```python
for index, model in enumerate(chain):
    if not pool.is_provider_healthy(provider_name):
        continue
    try:
        response = await self._guarded_call(model, ...)
        pool.report_success(provider_name)
        return response
    except Exception as exc:
        pool.report_failure(provider_name)
        errors.append((model, exc))
raise AllModelsExhaustedError(...)
```

This is a **sequential fallback** — it tries one model, waits for its response (or timeout), then tries the next. For a 3-model chain with 30s timeouts, a total failure could take 90+ seconds.

### PRV-003: No Provider Abstraction Layer

There is no `Provider` ABC or Protocol. Each provider's API details (URL format, auth method, model ID format) are embedded in the `post_request` method. Adding streaming support, function calling, or tool use would require modifying this single method.

### PRV-004: Provider Pool Self-Registration

In `execute_with_fallback` (rate_limiter.py:854-858):
```python
if pool is None:
    pool = self._default_pool
    for model in strategy.get_model_chain(role):
        provider_name = extract_provider_key(model)
        pool.register_provider(provider_name, roles=[role])
```

When no pool is passed, the method registers providers on-the-fly in the default pool. This means:
- Provider roles are set to `[role]` — a single provider registered for "breaker" role cannot also serve "generation"
- The `_default_pool` accumulates provider registrations across calls without cleanup

---

## 23. Streaming & Async Safety

### STR-001: Naive Datetime (HIGH-010)

`StreamEvent.timestamp` uses `datetime.utcnow()` — naive datetime. Use `datetime.now(timezone.utc)` or `core.validators.utc_now()`.

### STR-002: Emit Mutates Caller's Dict

`emit_raw` (streaming.py:318) calls `event_dict.pop("event", "progress")` which **modifies the caller's dict**. This is a side effect that callers may not expect.

### STR-003: Concurrent Stream Access

`StreamingManager` has three unprotected dicts:
```python
self._active_streams: dict[str, asyncio.Queue] = {}
self._stream_timestamps: dict[str, float] = {}
self._stream_tasks: dict[str, asyncio.Task] = {}
```

These are accessed from:
- Pipeline tasks (emit_event, close_stream)
- Background cleanup task (cleanup_stale_streams)
- HTTP response streaming (iter_events)

While asyncio is single-threaded, these dicts are modified without synchronization across tasks.

### ASY-001: Semaphore Bug in ResourceManager (MED-013)

```python
self.global_semaphore.release() if self.global_semaphore.locked() else None  # line 655
await asyncio.wait_for(self.global_semaphore.acquire(), timeout=0.001)  # line 656
```

This unconditionally releases a semaphore permit before acquiring. If the semaphore has fewer permits than the GLOBAL_CONCURRENCY_LIMIT, this inflates the permit count. Over time, this allows more concurrent requests than configured.

### ASY-002: Fire-and-Forget Tasks

`asyncio.create_task` without error handling appears in:
- `orchestrator/decisions.py` (lines 161, 175, 213, 289) — streaming events
- `core/runtime.py` (lines 295, 307, 342) — streaming events in dead code

### ASY-003: Task Cancellation on Pipeline Abort

In `stream_micro_mode` (pipelines.py:575-593):
```python
logician_task = asyncio.create_task(_run_agent("Logician", logician_sys))
creative_task = asyncio.create_task(_run_agent("Creative", creative_sys))
...
if isinstance(result, BaseException):
    logician_task.cancel()
    creative_task.cancel()
    return
```

If one agent fails, the other is cancelled. However, `task.cancel()` raises `asyncio.CancelledError` inside the coroutine. If the coroutine is in the middle of a network call (`gateway.execute_with_fallback`), the underlying HTTP request is not explicitly closed — it is left to the HTTP client's internal cancellation handling.

---

## 24. Race Conditions & Exception Handling

### RCE-001: EpistemicMemory Race Condition

`orchestrator/memory.py:32-37` and `39-54`:
The `record_failure` and `get_lessons_learned` methods access `self.failed_loops` without any synchronization. If called from concurrent pipeline executions (multiple requests), the deque operations interleave. While CPython's GIL protects individual deque operations, the compound read-update-write in `get_lessons_learned` is not atomic.

### RCE-002: TelemetryObserver Race Condition

`telemetry/observer.py:28-43`:
`track_usage` performs compound arithmetic on shared integer counters without any locking. Under concurrent requests, token counts and cost calculations could be inaccurate.

### RCE-003: ResourceManager Race Condition

`api_gateway/rate_limiter.py:628-669`:
`acquire_resources` modifies `provider_bucket.tokens`, `user_bucket.tokens`, and `self.request_history` without locks. Concurrent requests could cause:
- Token bucket reads/writes to race
- Request history to miss entries
- Semaphore accounting to be off

### EXH-001: Bare Except in Transition Blocks

7+ locations in pipelines.py:
```python
try:
    from orchestrator.conversation import ConversationState
    conversation_director.transition_state(session_id, ConversationState.FAILED)
except Exception:
    pass
```

This pattern:
1. Has an import statement inside the try block (deferred import pattern)
2. Catches ALL exceptions, including `KeyboardInterrupt` and `SystemExit`
3. Silently suppresses errors with no logging

### EXH-002: SecurityValidationError Type Confusion

Two different `SecurityValidationError` classes exist:
- `core.security.SecurityValidationError(ValueError)` — used by code actually calling the security validator
- `core.error_handlers.SecurityValidationError(AETHERISException)` — dead code

If a consumer catches `SecurityValidationError` and imports from the wrong module, the except clause will silently fail to catch the actual exception.

### EXH-003: AllModelsExhaustedError Wrapping

`api_gateway/rate_limiter.py:969-986`:
The exception class captures all errors, but the `__str__` method truncates error messages. For long chains with verbose error messages, the full error details might be lost.

---

## 25. Logging & Observability

### LOG-001: Inconsistent Logger Naming

| File | Logger Name |
|------|-------------|
| `agents/prompt_manager.py` | `aetheris.Agents.PromptManager` |
| `agents/parser.py` | `__name__` → `agents.parser` |
| `agents/prompt_utils.py` | `__name__` |
| `api_gateway/client.py` | `aetheris.Gateway.Client` |
| `api_gateway/rate_limiter.py` | `__name__` |
| `orchestrator/pipelines.py` | `__name__` |
| `orchestrator/streaming.py` | `__name__` |
| `orchestrator/evaluation.py` | `aetheris.Orchestrator.Evaluation` |
| `core/runtime.py` | `__name__` |
| `telemetry/observer.py` | `aetheris.Telemetry` |

Three different naming conventions:
1. `__name__` (standard Python, 7 modules)
2. `aetheris.Agents.PromptManager` (dotted hierarchical, 3 modules)
3. `aetheris.Telemetry` (flat, 1 module)

### LOG-002: Missing Correlation IDs

Most log statements in pipeline code do not include `request_id` or `session_id` in their extra fields. The EventType logging (streaming.py, state_machine.py) uses structured logging with `extra`, but pipeline.py evaluation messages use plain strings.

### LOG-003: print() in Telemetry (LOW-001)

`telemetry/observer.py:49-58`:
The `print_session_report` method was historically using `print()`. The code now shows `logger.info()` — this was fixed between the initial audit and current code. However, the function name still says "print".

### LOG-004: No Metrics Exposure

There is no HTTP endpoint that exposes:
- ProviderPool health status (circuit breaker state, cooldown)
- DecisionEngine rolling metrics (breaker pass rate, judge agreement rate)
- RuntimeEngine metrics (never collected)
- ResourceManager metrics (concurrent connections, queue size)

The `/api/providers/health` endpoint exists (server.py) but its implementation needs review.

### OBS-001: No Distributed Tracing

There is no distributed tracing integration. Pipeline execution across multiple stages, provider calls, and streaming events cannot be traced end-to-end. Debugging issues requires correlating log messages manually by `request_id`.

### OBS-002: Model IO Logging Not Rotated

`client.py:107-124` logs model I/O to `logs/model_io.log`. This file grows unboundedly. There is no log rotation, size limit, or retention policy.

---

## Issue Register — New Issues

### EXEC-004: Pipeline Double Conversation State Transition

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `orchestrator/pipelines.py` |
| **Lines** | 822-824, 869-875, 1133-1135 |
| **Function** | `_run_with_decision_engine` |
| **Description** | The DecisionEngine path calls `init_conversation_context` (creates session), then manually transitions to FAILED on abort (line 869-875), then calls `complete_conversation_session` (line 1133-1135) which calls `add_turn` and `transition_state` again. This double-transition attempt can raise `InvalidConversationTransitionError` (suppressed by the catch block). |
| **Root Cause** | Conversation management logic was duplicated between the init and completion functions without coordination. |
| **Suggested Fix** | Refactor conversation management: the pipeline should handle state transitions in one place, not split between init, inline error handling, and completion. |

### EXEC-005: User Query Not Added to Conversation History

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `agents/prompt_utils.py` |
| **Lines** | 206-251 |
| **Function** | `init_conversation_context` |
| **Description** | `init_conversation_context` retrieves history and checks truncation, but never adds the user's query as a turn. The user's turn is only added in `complete_conversation_session` (line 285), which adds the assistant's response. This means the user query is never recorded in the session history for multi-turn context. |
| **Root Cause** | The conversation init function was designed to fetch context, not to record the user's turn. The caller (pipeline) should add the user turn after init. |
| **Suggested Fix** | Add `conversation_director.add_turn(session_id, "user", user_query, token_count)` in the pipeline before generation, or modify `init_conversation_context` to accept and record the user query. |

### EXEC-006: DecisionEngine Streaming Events Fire-and-Forget

| Field | Value |
|-------|-------|
| **Severity** | High |
| **File** | `orchestrator/decisions.py` |
| **Lines** | 160-166, 174-181, 213-219, 289-295 |
| **Function** | `execute_breaker_gate`, `execute_generation_agents`, `execute_judge_synthesis` |
| **Description** | 4 locations use `asyncio.create_task(self.streaming_manager.emit_event(...))` without storing the task or attaching error handlers. If the streaming manager's queue is full or the stream is closed, the exception is silently lost. |
| **Root Cause** | Fire-and-forget pattern chosen for simplicity to avoid blocking during event emission. |
| **Suggested Fix** | Attach error handler: `task.add_done_callback(lambda t: logger.error(...) if t.exception() else None)`. Consider making event emission a fire-and-forget-but-logged pattern. |

### EXEC-007: ResourceManager Semaphore Token Bucket Inflation

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `api_gateway/rate_limiter.py` |
| **Lines** | 654-655 |
| **Function** | `acquire_resources` |
| **Description** | The semaphore is unconditionally released before acquiring, which inflates the permit count over time. The line `self.global_semaphore.release() if self.global_semaphore.locked() else None` always releases a permit even if none was held. |
| **Root Cause** | Buggy implementation — intended to check semaphore availability but incorrectly always releases. |
| **Suggested Fix** | Remove the release line entirely. Use `await self.global_semaphore.acquire()` directly with a timeout wrapper. |

### EXEC-008: Pipeline Error Helper Not Used

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `core/error_handlers.py`, `orchestrator/pipelines.py` |
| **Lines** | `error_handlers.py:223-249`, `pipelines.py:129-149` (and 6+ other blocks) |
| **Function** | `transition_conversation_to_failed`, `run_micro_mode`, `stream_micro_mode`, `_run_with_decision_engine` |
| **Description** | The helper `transition_conversation_to_failed` exists in `core/error_handlers.py` but is never called. Instead, 7+ identical 5-8 line blocks in pipelines.py reimplement the same logic with inline imports and bare except. |
| **Root Cause** | Helper was created after the duplicate patterns, and call sites were not updated. |
| **Suggested Fix** | Replace all 7+ blocks with `transition_conversation_to_failed(conversation_director, session_id, logger)`. |

### RES-005: AsyncHTTPClient Connection Pool Lifetime

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `api_gateway/client.py`, `api_gateway/rate_limiter.py` |
| **Lines** | `client.py:22`, `rate_limiter.py:837-839` |
| **Class** | `AsyncHTTPClient`, `AsyncAPIGateway` |
| **Description** | `AsyncHTTPClient` creates an `httpx.AsyncClient(timeout=600.0)` in `__init__`. The `close()` method exists but is never called during normal operation. The gateway's `close()` propagates to the client, but no entry point (`main.py`, `server.py`) ever calls `gateway.close()`. |
| **Root Cause** | Lifecycle management was not implemented for the HTTP client — it relies on process exit for cleanup. |
| **Suggested Fix** | Add proper lifecycle hooks in `main.py` and `server.py` to call `gateway.close()` on shutdown. |

### ASY-004: StreamingManager Dict Access Without Synchronization

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `orchestrator/streaming.py` |
| **Lines** | 96-98, 102-104, 106-138, 140-164, 168-243, 246-277, 281-298 |
| **Function** | All StreamingManager methods |
| **Description** | `_active_streams`, `_stream_timestamps`, and `_stream_tasks` are plain dicts accessed from multiple concurrent tasks. While asyncio is single-threaded and these accesses are technically safe within the event loop, the pattern is fragile and could break if any access is moved to a thread pool executor. |
| **Root Cause** | Developer assumed single-threaded asyncio safety without considering thread pool executors or future changes. |
| **Suggested Fix** | Add `threading.Lock` or use `asyncio.Lock` for all dict mutations to document the synchronization requirement. |

### TOK-004: Instruction Reinforcement Schema Mismatch

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `api_gateway/client.py` |
| **Lines** | 47-49 |
| **Function** | `post_request` |
| **Description** | The "CRITICAL REMINDER" message instructs the model to output exactly 3 keys (`reasoning_steps`, `answer`, `confidence`). However, the Judge (synthesizer) call uses `aetherisOutput` which requires 5 keys (`final_answer`, `overall_confidence`, `overall_bias_risk`, `disagreement_notes`, `validation_score`). The reminder conflicts with the judge's expected schema, potentially confusing the model. |
| **Root Cause** | Generic reinforcement message added without considering the judge's different output schema. |
| **Suggested Fix** | Make the instruction reinforcement role-aware: send a different reminder for generation roles (AgentOutput schema) vs. judge roles (aetherisOutput schema). |

### CTX-003: Breaker Receives Full Heavy Context

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `agents/prompt_manager.py`, `agents/prompt_utils.py` |
| **Lines** | 276-338, 52-72 |
| **Function** | `assemble_agent_prompt`, `assemble_breaker_prompt` |
| **Description** | The Breaker agent (designed as "lightweight, fast pre-filter" with a 100ms timeout) receives all 12 runtime contracts (~2000 tokens) plus the agent-specific prompt. This heavy context is at odds with the Breaker's mandate for brevity and speed. |
| **Root Cause** | All agents use the same prompt assembly pipeline with the same runtime contracts. |
| **Suggested Fix** | Consider reducing runtime contracts for the Breaker to only essential ones (security, error handling). Or implement a lightweight prompt profile for gate agents. |

### LOG-004: Missing Structured Logging in Pipeline

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `orchestrator/pipelines.py`, `orchestrator/decisions.py` |
| **Lines** | Multiple |
| **Function** | Various |
| **Description** | Most log statements in pipeline code use plain string formatting instead of structured logging with `extra` fields. `state_machine.py` and `streaming.py` use structured logging with `extra={"request_id": ..., "stage": ...}`, but `pipelines.py`, `decisions.py`, and `evaluation.py` do not. |
| **Root Cause** | Incremental adoption — structured logging was added to some modules but not retrofitted to older ones. |
| **Suggested Fix** | Add `extra` fields to all log statements in `pipelines.py`, `decisions.py`, and `evaluation.py` for consistent correlation across components. |

### OBS-003: No Provider Health Metrics Endpoint

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `server.py` |
| **Lines** | — |
| **Class** | — |
| **Description** | There is no HTTP endpoint that exposes ProviderPool health status (circuit breaker state, cooldown, degradation level). The frontend health polling (30s interval) has no way to display per-provider health status or circuit breaker state. |
| **Root Cause** | ProviderPool metrics are not exposed via the API. |
| **Suggested Fix** | Add a `GET /api/providers/health` endpoint that returns `ProviderPool.get_all_statuses()` enriched with `ResourceManager.get_resource_metrics()`. |

---

## Summary Statistics

| Category | New Issues | Existing Issues | Total |
|----------|-----------|-----------------|-------|
| Execution | 4 | 8 | 12 |
| Resource | 2 | 3 | 5 |
| Memory | 0 | 2 | 2 |
| Token/Context | 4 | 2 | 6 |
| Provider | 2 | 3 | 5 |
| Streaming | 1 | 3 | 4 |
| Async | 3 | 2 | 5 |
| Race Conditions | 1 | 2 | 3 |
| Exception Handling | 3 | 3 | 6 |
| Logging | 2 | 3 | 5 |
| Observability | 1 | 1 | 2 |
| **Total** | **23** | **32** | **55** |

**Overall Assessment:** The AETHERIS backend has solid architectural foundations with well-separated concerns, proper async patterns, and comprehensive validation. The primary risks are: (1) dead code paths that bypass contract enforcement, (2) dual pipeline execution paths with duplicated logic, (3) in-memory-only state that prevents recovery from failures, (4) fire-and-forget async patterns that silently lose errors, and (5) lack of test coverage for all orchestration logic.
