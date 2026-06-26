# aetheris API Documentation

## Endpoints

### 1. Sessions Management

- **`POST /sessions`**
  - **Description**: Create a new conversation session.
  - **Request Body**: `{"session_id": "optional-uuid", "user_id": "optional-uuid"}`
  - **Response**: `{"session_id": "uuid", "state": "active", "created_at": "timestamp"}`

- **`GET /sessions/{session_id}`**
  - **Description**: Retrieve session metadata.
  - **Response**: `{"session_id": "uuid", "turn_count": 0, "total_tokens": 0, "state": "active", "remaining_capacity": 128000}`

- **`GET /sessions/{session_id}/history`**
  - **Description**: Retrieve conversation history.
  - **Response**: `[{"role": "user", "content": "hello", "timestamp": "time", "token_count": 10}]`

- **`DELETE /sessions/{session_id}`**
  - **Description**: Explicitly close a session.
  - **Response**: `{"session_id": "uuid", "state": "completed", "closed_at": "timestamp"}`

### 2. Checkpoints Management

- **`GET /checkpoints/{request_id}`**
  - **Description**: List checkpoints for a request.
  - **Response**: `[{"checkpoint_id": "uuid", "stage": "generation", "timestamp": "time", "expires_at": "time"}]`

- **`POST /checkpoints/{checkpoint_id}/restore`**
  - **Description**: Resume pipeline from a checkpoint.
  - **Response**: `{"request_id": "uuid", "resumed_from_stage": "generation", "status": "success"}`

- **`DELETE /checkpoints/{request_id}`**
  - **Description**: Delete checkpoints for a request.
  - **Response**: `{"request_id": "uuid", "deleted_count": 2}`

### 3. Provider Health & Telemetry

- **`GET /providers/health`**
  - **Description**: Get health metrics for all providers.
  - **Response**: `[{"provider_name": "openrouter", "health_status": "healthy", "error_rate": 0.0, "mean_latency_ms": 200, "success_rate": 1.0, "circuit_breaker_state": "CLOSED", "last_success_timestamp": "time", "last_failure_timestamp": null}]`

- **`POST /providers/{provider_name}/recovery`**
  - **Description**: Manually trigger recovery for a provider.
  - **Response**: `{"provider_name": "openrouter", "status": "recovered", "health_status": "healthy"}`

- **`GET /telemetry`**
  - **Description**: Get aggregated telemetry metrics.
  - **Response**: `{"decision_metrics": {...}, "resource_metrics": {...}, "security_metrics": {...}, "timestamp": "time"}`

## System Limits and Contracts

### Rate Limits
- **Per Provider**: 100 requests / minute
- **Per User**: 50 requests / minute
- **Global Concurrency**: 100 concurrent requests

### Timeouts
- **Breaker Gate**: 100ms
- **Parallel Agents**: 30s
- **Checkpoint Save**: 5s
- **Checkpoint Restore**: 10s
- **Default Execution**: 120s

### Security Constraints
- **Character Limit**: 10,000 characters
- **Validation**: UTF-8 valid characters only
- **Injection Detection**: Advanced prompt injection matching ("ignore previous instructions", etc.)
- **Data Safety**: Automatic secret scrubbing (API keys, passwords, tokens) replaced with `[REDACTED]`

### Conversation Limits
- **Max Turns**: 100 turns per session
- **Context Window**: 128,000 tokens
- **Compression**: Triggers at 80% capacity; 5 most recent turns preserved
