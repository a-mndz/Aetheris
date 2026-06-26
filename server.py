"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Web Server: FastAPI backend serving the web UI and pipeline API.

Launch with:  python main.py --web
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api_gateway import AsyncAPIGateway, ProviderPool, ProviderStrategy
from api_gateway.rate_limiter import extract_provider_key
from core.config import get_settings
from core.database import get_db, engine
from core.models import Base, User
from core.security import (
    SecurityValidationError,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from orchestrator import run_micro_mode, stream_micro_mode
from orchestrator.aetheris_orchestrator import initialize_aetheris_components, create_request_passport
from orchestrator.background_tasks import create_background_tasks, cancel_background_tasks
from orchestrator.conversation import ConversationState
from orchestrator.pipelines import _build_frontend_payload
from orchestrator.streaming import EventType, StreamEvent, StreamingManager
from api_gateway.rate_limiter import (
    extract_provider_key,
    ProviderStatus,
    CircuitBreakerState,
    HealthMetrics,
)
from telemetry.observer import observer

logger = logging.getLogger("aetheris.web")

_PIPELINE_TIMEOUT_SEC = 900

# ── Global infrastructure (initialised in lifespan) ─────────────────────
_gateway: AsyncAPIGateway | None = None
_strategy: ProviderStrategy | None = None
_pool: ProviderPool | None = None
_streaming_mgr: StreamingManager = StreamingManager()
_aetheris: dict[str, Any] = {}
_background_tasks: list[asyncio.Task] = []


def _bootstrap_pool(strategy: ProviderStrategy) -> ProviderPool:
    """Create a ProviderPool and register every model from the strategy."""
    pool = ProviderPool()
    model_roles: dict[str, set[str]] = {}
    for role in strategy.supported_roles:
        for model in strategy.get_model_chain(role):
            model_roles.setdefault(model, set()).add(role)
    for model, roles in model_roles.items():
        pool.register_provider(extract_provider_key(model), roles=sorted(roles))
    return pool


# ── Application Lifespan ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _gateway, _strategy, _pool, _streaming_mgr, _aetheris

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format=settings.LOG_FORMAT,
    )

    # Auto-create tables on startup
    logger.info("Initializing database tables on startup...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        logger.warning("Database connection failed: %s. Attempting to start PostgreSQL server...", exc)
        import subprocess
        try:
            pg_ctl_path = r"C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
            data_dir = r"C:\Program Files\PostgreSQL\18\data"
            subprocess.run([pg_ctl_path, "start", "-D", data_dir], shell=True, check=False)
            # Give the server a few seconds to initialize
            await asyncio.sleep(4)
            # Retry connection
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL started successfully and tables initialized.")
        except Exception as retry_exc:
            logger.error("Could not automatically start PostgreSQL server: %s", retry_exc)
            raise exc

    global _background_tasks

    _strategy = ProviderStrategy(mode="HYBRID")
    _pool = _bootstrap_pool(_strategy)
    _gateway = AsyncAPIGateway()
    _aetheris = initialize_aetheris_components()

    # Create background tasks for cleanup operations
    # Add streaming_manager to aetheris components if not already present
    aetheris_with_streaming = dict(_aetheris)
    if "streaming_manager" not in aetheris_with_streaming:
        aetheris_with_streaming["streaming_manager"] = _streaming_mgr
    _background_tasks = create_background_tasks(aetheris_with_streaming)

    logger.info(
        "aetheris Web Server ready — mode=%s, providers=%d, background_tasks=%d",
        _strategy.mode.value,
        len(_pool.get_all_statuses()) if _pool else 0,
        len(_background_tasks),
    )
    yield

    # Cancel all background tasks gracefully
    if _background_tasks:
        logger.info("Cancelling %d background tasks...", len(_background_tasks))
        await cancel_background_tasks(_background_tasks)
        logger.info("All background tasks cancelled gracefully.")

    if _gateway:
        await _gateway.close()
    observer.print_session_report()
    logger.info("aetheris Web Server shut down.")


app = FastAPI(title="aetheris", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent / "aetheris-ui" / "dist"


# ── Request / Response Models ───────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    query: str
    history: list[Message] | None = None


# ── Auth Request Schemas ──────────────────────────────────────────────────

class AuthRequest(BaseModel):
    email: str
    password: str


# ── Session Management Schemas ────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None


class SessionCreateResponse(BaseModel):
    session_id: str
    state: str
    created_at: str


class SessionMetadataResponse(BaseModel):
    session_id: str
    turn_count: int
    total_tokens: int
    state: str
    remaining_capacity: int


class SessionHistoryResponse(BaseModel):
    history: list[dict[str, str]]


class SessionCloseResponse(BaseModel):
    session_id: str
    state: str
    closed_at: str


# ── Checkpoint Management Schemas ─────────────────────────────────────────

class CheckpointListResponse(BaseModel):
    checkpoints: list[dict[str, str]]


class CheckpointRestoreRequest(BaseModel):
    pass


class CheckpointRestoreResponse(BaseModel):
    request_id: str
    resumed_from_stage: str
    status: str


class CheckpointDeleteResponse(BaseModel):
    request_id: str
    deleted_count: int


# ── Provider Health Schemas ───────────────────────────────────────────────

class ProviderHealthResponse(BaseModel):
    provider_name: str
    health_status: str
    error_rate: float
    mean_latency_ms: float
    success_rate: float
    circuit_breaker_state: str
    last_success_timestamp: float | None = None
    last_failure_timestamp: float | None = None


class ProviderRecoveryRequest(BaseModel):
    pass


class ProviderRecoveryResponse(BaseModel):
    provider_name: str
    status: str
    health_status: str | None = None
    retry_after_sec: float | None = None


# ── Auth and Page Serving Routes ─────────────────────────────────────────

@app.get("/login")
async def serve_login():
    """Serve the login HTML page."""
    login_path = Path(__file__).parent / "aetheris_login.html"
    if not login_path.exists():
        raise HTTPException(status_code=404, detail="Login page not found.")
    return FileResponse(login_path, media_type="text/html")


@app.post("/auth/register", status_code=201)
async def register_user(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user, checking if the email already exists."""
    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    if result.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Hash the password and store the user
    hashed = hash_password(req.password)
    new_user = User(email=req.email, password_hash=hashed)
    db.add(new_user)
    await db.commit()
    return {"message": "User registered successfully"}


@app.post("/auth/login")
async def login_user(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate credentials and generate a JWT access token."""
    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate token
    token = create_access_token(data={"sub": user.email})
    return {
        "access_token": token,
        "token_type": "bearer"
    }


# ── API Endpoints ───────────────────────────────────────────────────────

@app.post("/api/query")
async def handle_query(
    req: QueryRequest,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Run the micro-mode pipeline for a user query."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        history_list = [msg.model_dump() for msg in req.history] if req.history else None
        session_id = str(uuid.uuid4())
        passport = create_request_passport()
        result = await asyncio.wait_for(
            run_micro_mode(
                user_query=req.query.strip(),
                gateway=_gateway,
                strategy=_strategy,
                pool=_pool,
                history=history_list,
                decision_engine=_aetheris.get("decision_engine"),
                reasoning_graph=_aetheris.get("reasoning_graph"),
                claim_manager=_aetheris.get("claim_manager"),
                streaming_manager=_aetheris.get("streaming_manager"),
                conversation_director=_aetheris.get("conversation_director"),
                session_id=session_id,
            ),
            timeout=_PIPELINE_TIMEOUT_SEC,
        )

        result["_passport"] = passport.to_dict()
        return JSONResponse(_build_frontend_payload(result))

    except SecurityValidationError as exc:
        return JSONResponse(exc.to_error_response(), status_code=400)
    except asyncio.TimeoutError:
        return JSONResponse(
            {
                "status": "error",
                "answer": f"Pipeline timed out after {_PIPELINE_TIMEOUT_SEC}s.",
                "confidence_score": 0.0,
                "bias_risk": "Unknown",
                "decision": None,
                "agent_outputs": {
                    "logician": None,
                    "creative": None,
                }
            },
            status_code=504,
        )
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        return JSONResponse(
            {
                "status": "error",
                "answer": f"{type(exc).__name__}: {exc}",
                "confidence_score": 0.0,
                "bias_risk": "Unknown",
                "decision": None,
                "agent_outputs": {
                    "logician": None,
                    "creative": None,
                }
            },
            status_code=500,
        )


@app.post("/api/query/stream")
async def handle_query_stream(
    req: QueryRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the micro-mode pipeline as Server-Sent Events.

    Each event is a JSON-encoded SSE data line.  The frontend reads the
    response via ``fetch()`` + ``ReadableStream`` and updates the UI
    in real time as each pipeline stage completes.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    request_id = str(uuid.uuid4())
    history_list = [msg.model_dump() for msg in req.history] if req.history else None

    try:
        _streaming_mgr.create_stream(request_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    async def _forward_pipeline_events():
        """Forward events from stream_micro_mode into the StreamingManager."""
        try:
            async for event in stream_micro_mode(
                user_query=req.query.strip(),
                gateway=_gateway,
                strategy=_strategy,
                pool=_pool,
                history=history_list,
            ):
                event_type_str = event.pop("event", "progress")
                try:
                    event_type = EventType(event_type_str)
                except ValueError:
                    event_type = EventType.PROGRESS
                    event["original_event"] = event_type_str

                await _streaming_mgr.emit_event(
                    request_id,
                    StreamEvent(event=event_type, data=event),
                )
        except asyncio.CancelledError:
            logger.info("Pipeline forwarder cancelled for request_id=%s.", request_id)
        except Exception as exc:
            logger.exception("Pipeline forwarder error: %s", exc)
            await _streaming_mgr.emit(
                request_id,
                EventType.ERROR,
                {"stage": "unknown", "message": f"{type(exc).__name__}: {exc}"},
            )
        finally:
            # Put sentinel to signal end of stream
            queue = _streaming_mgr._active_streams.get(request_id)
            if queue is not None:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

    async def event_generator():
        # Start pipeline execution as background task
        forward_task = asyncio.create_task(_forward_pipeline_events())

        try:
            async for sse_event in _streaming_mgr.iter_events(request_id):
                yield f"data: {json.dumps(sse_event)}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled by client for request_id=%s.", request_id)
        except Exception as exc:
            logger.exception("SSE stream error: %s", exc)
            error_event = {
                "event": "error",
                "data": {"stage": "unknown", "message": f"{type(exc).__name__}: {exc}"},
                "timestamp": datetime.utcnow().isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass
            _streaming_mgr.close_stream(request_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/status")
async def get_status(current_user: User = Depends(get_current_user)) -> dict:
    """Return provider health + session telemetry."""
    return {
        "providers": _pool.get_all_statuses() if _pool else [],
        "telemetry": {
            "total_calls": observer.transaction_count,
            "total_input_tokens": observer.total_input_tokens,
            "total_output_tokens": observer.total_output_tokens,
            "total_cost_usd": round(observer.accumulated_cost_usd, 6),
        },
        "mode": _strategy.mode.value if _strategy else "UNKNOWN",
    }


@app.get("/api/telemetry")
async def get_telemetry(current_user: User = Depends(get_current_user)) -> dict:
    """Return session telemetry metrics."""
    return {
        "total_calls": observer.transaction_count,
        "total_input_tokens": observer.total_input_tokens,
        "total_output_tokens": observer.total_output_tokens,
        "total_cost_usd": round(observer.accumulated_cost_usd, 6),
    }


@app.get("/api/config")
async def get_config(current_user: User = Depends(get_current_user)) -> dict:
    """Return non-sensitive configuration."""
    settings = get_settings()
    return {
        "mode": _strategy.mode.value if _strategy else "UNKNOWN",
        "roles": _strategy.supported_roles if _strategy else [],
        "simulation_mode": not settings.OPENROUTER_API_KEY,
        "log_level": settings.LOG_LEVEL,
    }


# ── Session Management Endpoints ──────────────────────────────────────────

@app.post("/api/sessions", response_model=SessionCreateResponse, status_code=201)
async def create_session(
    req: SessionCreateRequest,
    current_user: User = Depends(get_current_user),
) -> SessionCreateResponse:
    """Create a new conversation session."""
    import uuid
    from datetime import datetime, timezone

    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    session_id = req.session_id or str(uuid.uuid4())
    user_id = req.user_id or current_user.email

    try:
        session = conversation_director.create_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return SessionCreateResponse(
        session_id=session.session_id,
        state=session.state.value,
        created_at=session.created_at.isoformat(),
    )


@app.get("/api/sessions/{session_id}", response_model=SessionMetadataResponse)
async def get_session_metadata(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> SessionMetadataResponse:
    """Retrieve session metadata."""
    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    try:
        metadata = conversation_director.get_metadata(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return SessionMetadataResponse(**metadata)


@app.get("/api/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> SessionHistoryResponse:
    """Retrieve conversation history."""
    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    try:
        history = conversation_director.get_history(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return SessionHistoryResponse(history=history)


@app.delete("/api/sessions/{session_id}", response_model=SessionCloseResponse)
async def close_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> SessionCloseResponse:
    """Explicitly close a conversation session."""
    from datetime import datetime

    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    try:
        conversation_director.transition_state(session_id, ConversationState.COMPLETED)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return SessionCloseResponse(
        session_id=session_id,
        state="completed",
        closed_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Checkpoint Management Endpoints ───────────────────────────────────────

@app.get("/api/checkpoints/{request_id}", response_model=CheckpointListResponse)
async def list_checkpoints(
    request_id: str,
    current_user: User = Depends(get_current_user),
) -> CheckpointListResponse:
    """List checkpoints for a request."""
    checkpoint_manager = _aetheris.get("checkpoint_manager")
    if not checkpoint_manager:
        raise HTTPException(status_code=503, detail="Checkpoint manager not available")

    try:
        checkpoints = await checkpoint_manager.list_checkpoints(request_id=request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    checkpoint_list = [
        {
            "checkpoint_id": cp.checkpoint_id,
            "stage": cp.stage,
            "timestamp": cp.timestamp.isoformat(),
            "expires_at": cp.expires_at.isoformat(),
        }
        for cp in checkpoints
    ]

    return CheckpointListResponse(checkpoints=checkpoint_list)


@app.post("/api/checkpoints/{checkpoint_id}/restore", response_model=CheckpointRestoreResponse)
async def restore_checkpoint(
    checkpoint_id: str,
    req: CheckpointRestoreRequest,
    current_user: User = Depends(get_current_user),
) -> CheckpointRestoreResponse:
    """Resume pipeline from a checkpoint."""
    checkpoint_manager = _aetheris.get("checkpoint_manager")
    if not checkpoint_manager:
        raise HTTPException(status_code=503, detail="Checkpoint manager not available")

    try:
        checkpoint = await checkpoint_manager.restore_checkpoint(checkpoint_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found or expired")

    return CheckpointRestoreResponse(
        request_id=checkpoint.request_id,
        resumed_from_stage=checkpoint.stage,
        status="restored",
    )


@app.delete("/api/checkpoints/{request_id}", response_model=CheckpointDeleteResponse)
async def delete_checkpoints(
    request_id: str,
    current_user: User = Depends(get_current_user),
) -> CheckpointDeleteResponse:
    """Delete all checkpoints for a request."""
    checkpoint_manager = _aetheris.get("checkpoint_manager")
    if not checkpoint_manager:
        raise HTTPException(status_code=503, detail="Checkpoint manager not available")

    try:
        deleted_count = await checkpoint_manager.delete_checkpoints(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return CheckpointDeleteResponse(
        request_id=request_id,
        deleted_count=deleted_count,
    )


# ── Provider Health Monitoring Endpoints ──────────────────────────────────

@app.get("/api/providers/health", response_model=list[ProviderHealthResponse])
async def get_providers_health(
    current_user: User = Depends(get_current_user),
) -> list[ProviderHealthResponse]:
    """Return health metrics for all registered providers."""
    if not _pool:
        return []

    health_list = []
    for provider_name in _pool._priority_order:
        if provider_name not in _pool._providers:
            continue

        state = _pool._providers[provider_name]
        metrics = _pool.get_health_metrics(provider_name)
        health_status = _pool.calculate_health_status(provider_name)

        if metrics is None:
            metrics = HealthMetrics()

        health_list.append(
            ProviderHealthResponse(
                provider_name=provider_name,
                health_status=health_status,
                error_rate=metrics.error_rate,
                mean_latency_ms=metrics.mean_latency_ms,
                success_rate=metrics.success_rate,
                circuit_breaker_state=state.circuit_breaker_state.value,
                last_success_timestamp=state.last_success_timestamp,
                last_failure_timestamp=state.last_failure_timestamp,
            )
        )

    return health_list


@app.post("/api/providers/{provider_name}/recovery", response_model=ProviderRecoveryResponse)
async def trigger_provider_recovery(
    provider_name: str,
    req: ProviderRecoveryRequest,
    current_user: User = Depends(get_current_user),
) -> ProviderRecoveryResponse:
    """Manually trigger recovery for a DEAD provider."""
    if not _pool:
        raise HTTPException(status_code=503, detail="Provider pool not available")

    if provider_name not in _pool._providers:
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")

    state = _pool._providers[provider_name]
    if state.status is not ProviderStatus.DEAD:
        return ProviderRecoveryResponse(
            provider_name=provider_name,
            status="already_healthy",
            health_status=state.status.value,
        )

    recovery_success = _pool.attempt_recovery(provider_name)

    if recovery_success:
        updated_state = _pool._providers[provider_name]
        return ProviderRecoveryResponse(
            provider_name=provider_name,
            status="recovered",
            health_status=updated_state.status.value,
        )
    else:
        # Calculate retry-after based on backoff delay
        retry_after = state.backoff_delay if state.backoff_delay > 0 else 60.0
        return ProviderRecoveryResponse(
            provider_name=provider_name,
            status="recovery_failed",
            health_status=state.status.value,
            retry_after_sec=retry_after,
        )


# ── Static File Serving ─────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    """Serve the main HTML page."""
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found.")
    return FileResponse(index, media_type="text/html")


if (WEB_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")
