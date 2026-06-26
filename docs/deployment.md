# AETHERIS Deployment and Rollback Procedures

This document outlines the deployment strategy, rollback procedures, and observability mechanisms for integrating the AETHERIS architecture into the existing aetheris environment.

## Deployment Steps

Deployment occurs iteratively across 5 distinct phases to minimize risk and preserve backward compatibility.

### Phase 1: Deploy Core Components
1. Deploy `ExecutionPassport`, `SecurityValidator`, and `StateMachine`.
2. Migrate existing API endpoints to generate an `ExecutionPassport` for all requests.
3. Enable security validation checks at API boundaries.
4. Establish base state transitions in `StateMachine`.
5. **Validation**: Run core unit tests ensuring UUID v4 generation, thread-safety, and injection detection succeed.

### Phase 2: Deploy Orchestration Components
1. Deploy `ConversationDirector`, `CheckpointManager`, and `DecisionEngine`.
2. Introduce multi-turn state context to backend tracking via Session ID logic.
3. Implement 5s persistent checkpoint saving after `Normalize` and `Breach_Check`.
4. Replace legacy decision branching with `DecisionEngine` parallel gates.
5. **Validation**: Test 30-second parallelism and session memory retention algorithms.

### Phase 3: Deploy Knowledge Components
1. Deploy `ReasoningGraph`, `ClaimManager`, and `MemoryManager`.
2. Configure token-counting heuristics (tiktoken mappings) and 80% boundary truncation.
3. Connect knowledge pipelines to output verification so `ClaimManager` logs facts to `ReasoningGraph`.
4. **Validation**: Confirm pattern storage and semantic expiration constraints.

### Phase 4: Deploy Observability Components
1. Deploy `StreamingManager` and `RuntimeEngine`.
2. Migrate legacy synchronous loops to async Server-Sent Events (SSE) emitters.
3. Wrap all actions in `RuntimeEngine` for contract enforcement verification.
4. **Validation**: Subscribe frontend clients to verify sub-500ms latency stream compliance.

### Phase 5: Deploy Integration
1. Deploy AETHERIS pipeline orchestrator logic integrating all systems.
2. Initialize and deploy FastAPI background tasks (`cleanup_expired_sessions_task`, `expire_checkpoints_task`, etc.).
3. **Validation**: Full End-to-End integration tests confirming complete architecture lifecycle.

## Rollback Procedures

### For Each Phase:
- **Database Migration Reversal**: Execute reverse SQL migrations or document stores scripts explicitly tagged to the Phase version. Remove any table schemas tied to `ReasoningGraph` (Phase 3) or `CheckpointManager` (Phase 2) if necessary.
- **Deployment Reversion**: Restore previous container tags or revert source commits corresponding to the stable pre-phase state. E.g., `git checkout tags/v-pre-phase-2`.
- **State Restoration**: Empty in-memory `ProviderPool` metrics and clear active conversation tokens to prevent misaligned session histories.

## Monitoring and Alerting

To ensure stability post-deployment, observe the following telemetry:

- **Metrics to Monitor**:
  - `error_rate`: Tracks 500s or timeouts across providers.
  - `latency_ms`: Focus on Breaker Gate <100ms, and complete pipeline resolution.
  - `queue_depth`: Request queue size via `ResourceManager`.
  - `injection_attempt_count`: Indicates adversarial surges.

- **Alert Thresholds**:
  - **High Latency**: Pipeline P95 > 10,000ms.
  - **Queue Full**: Request queue exceeds 900.
  - **Degraded Providers**: Primary provider `error_rate` exceeds 20%.

- **Runbooks**:
  - *Circuit Breaker Opened*: Check provider API status page. Verify fallback LLM chains in `ProviderRegistry` are handling overflow traffic correctly.
  - *Rate Limit Saturated*: Dynamically inject higher user token boundaries if infrastructure allows, or scale gateway horizontally.

## Performance Tuning

Fine-tuning operational thresholds depending on infrastructure scale:

- **Rate Limit Adjustment**: Modifiable via `ResourceManager` for premium users or internal service accounts to exceed standard 50 req/min limits.
- **Token Bucket Capacity**: By default 10 tokens. Can be tuned higher to absorb bursty asynchronous workloads from clients.
- **Compression Thresholds**: Max context limits depend heavily on model context windows (e.g., 128k for modern large models). Truncation threshold at 80% and rejection at 90% can be lowered for memory conservation.
- **Circuit Breaker Parameters**: Failure threshold (default 5) and cooldown periods (default 60s) can be relaxed if network instability is common but provider itself remains healthy.
