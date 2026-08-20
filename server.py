"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Web Server: FastAPI backend serving the web UI and pipeline API.

Launch with:  python main.py --web
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator
from pydantic import Field as PField
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# CRIT-007: load provider API keys from the OS secret store BEFORE
# anything that transitively imports ``core.config``.  Idempotent —
# safe to call even when ``main.py`` has already done so.
import secrets_bootstrap  # noqa: F401  (side-effecting import)
from api_gateway import AsyncAPIGateway, ProviderPool, ProviderStrategy
from api_gateway.rate_limiter import (
    HealthMetrics,
    ProviderStatus,
    extract_provider_key,
)
from core.config import configure_logging, get_settings
from core.database import get_db, verify_schema_current
from core.models import ConversationMessageRecord, ConversationSessionRecord, User
from core.security import (
    SecurityValidationError,
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from orchestrator import metrics
from orchestrator.aetheris_orchestrator import create_request_passport, initialize_aetheris_components
from orchestrator.background_tasks import cancel_background_tasks, create_background_tasks
from orchestrator.conversation import ConversationState
from orchestrator.pipelines import _build_frontend_payload
from orchestrator.streaming import EventType, StreamingManager
from telemetry.observer import observer

logger = logging.getLogger("aetheris.web")

_PIPELINE_TIMEOUT_SEC = 900
_MAX_REQUEST_BODY_BYTES = 100_000

# ── Global infrastructure (initialised in lifespan) ─────────────────────
_gateway: AsyncAPIGateway | None = None
_strategy: ProviderStrategy | None = None
_pool: ProviderPool | None = None
_streaming_mgr: StreamingManager = StreamingManager()
_aetheris: dict[str, Any] = {}
_background_tasks: list[asyncio.Task] = []

# HIGH-014 — fixed-window in-process limiter for /auth/* routes.
_auth_rate_log: dict[str, list[float]] = {}
_AUTH_RATE_WINDOW_SEC = 60.0


def _enforce_auth_rate_limit(client_ip: str) -> bool:
    """Return True if the IP is allowed to make another auth request."""
    now = datetime.now(timezone.utc).timestamp()
    settings = get_settings()
    limit = max(1, int(settings.AUTH_RATE_LIMIT_PER_MINUTE))
    history = _auth_rate_log.setdefault(client_ip, [])
    history[:] = [t for t in history if now - t < _AUTH_RATE_WINDOW_SEC]
    if len(history) >= limit:
        return False
    history.append(now)
    return True


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


def _resolve_cors_origins() -> list[str]:
    """CRIT-004: derive explicit allowlist from CORS_ORIGINS env var."""
    raw = get_settings().CORS_ORIGINS
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if any(o == "*" for o in origins):
        raise RuntimeError(
            "CRIT-004: CORS_ORIGINS cannot contain '*'.  Provide an explicit "
            "allowlist of fully-qualified origins."
        )
    if not origins:
        raise RuntimeError(
            "CRIT-004: CORS_ORIGINS must contain at least one explicit origin."
        )
    return origins


# ── Application Lifespan ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _gateway, _strategy, _pool, _streaming_mgr, _aetheris

    settings = get_settings()
    configure_logging(settings)

    logger.info("Verifying PostgreSQL schema revision...")
    try:
        await verify_schema_current()
    except Exception as exc:
        logger.error("PostgreSQL schema verification failed at startup: %s", exc)
        raise RuntimeError(
            "PostgreSQL is unreachable or not at the required Alembic revision. "
            "Verify DATABASE_URL and run 'alembic upgrade head'."
        ) from exc

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


@app.middleware("http")
async def request_body_size_limit(request: Request, call_next):
    """Reject oversized request bodies before validation or provider work."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_REQUEST_BODY_BYTES:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > _MAX_REQUEST_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
    request._body = bytes(body)
    return await call_next(request)


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    """MED-019 lightweight CSRF origin check for state-changing requests.

    Browsers carry the Origin header on cross-site requests; we verify that
    incoming Origin / Referer hosts match the CORS allowlist before any
    POST / PUT / DELETE handler runs.  Health probes and GETs are skipped.
    """
    if request.method.upper() not in {"POST", "PUT", "DELETE", "PATCH"}:
        return await call_next(request)

    settings = get_settings()
    cookie_authenticated = (
        settings.AUTH_COOKIE_NAME in request.cookies
        and "authorization" not in request.headers
    )
    try:
        allowlist = _resolve_cors_origins()
    except RuntimeError:
        if cookie_authenticated:
            return JSONResponse(
                {"status": "error", "error": "CSRF origin policy unavailable"},
                status_code=503,
            )
        return await call_next(request)

    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if not origin:
        if cookie_authenticated:
            return JSONResponse(
                {"status": "error", "error": "CSRF origin required"},
                status_code=403,
            )
        return await call_next(request)

    from urllib.parse import urlparse
    parsed = urlparse(origin)
    candidate = f"{parsed.scheme}://{parsed.netloc}"
    if candidate not in allowlist:
        return JSONResponse(
            {"status": "error", "error": "CSRF check failed (origin not in allowlist)"},
            status_code=403,
        )
    return await call_next(request)


# CRIT-004 audit fix: CORS middleware uses an explicit allowlist (no wildcards).
app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent / "frontend" / "dist"


# ── Request / Response Models ───────────────────────────────────────────

class _StrictRequestModel(BaseModel):
    """Base for public API ingress payloads (RFC-001 §4 critical contract).

    Unknown fields are rejected rather than silently ignored, so malformed
    or unexpected client payloads fail fast instead of masking bugs. Response
    models stay on plain ``BaseModel`` — only inbound request bodies are
    critical contracts. Superseded by ``AetherisBaseModel`` once RFC-007
    Step 2 lands ``core/base.py``.
    """

    model_config = ConfigDict(extra="forbid")


class Message(_StrictRequestModel):
    role: Literal["user", "assistant"]
    content: str = PField(min_length=1, max_length=10_000)


class QueryRequest(_StrictRequestModel):
    query: str = PField(min_length=1, max_length=10_000)
    history: list[Message] | None = PField(default=None, max_length=50)

    @model_validator(mode="after")
    def _bound_history(self) -> "QueryRequest":
        if self.history and sum(len(message.content) for message in self.history) > 50_000:
            raise ValueError("history content must not exceed 50000 characters")
        return self


# ── Auth Request Schemas ──────────────────────────────────────────────────

class AuthLoginRequest(_StrictRequestModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        normalised = value.strip().lower()
        if "@" not in normalised or " " in normalised or len(normalised) > 254:
            raise ValueError("email must be a well-formed address")
        return normalised

class AuthRegisterRequest(AuthLoginRequest):
    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, value: str) -> str:
        # MED-021 audit fix: enforce minimum strength baseline so trivially
        # guessable passwords cannot be registered.
        if len(value) < 8:
            raise ValueError("password must be at least 8 characters long")
        if len(set(value)) < 3:
            raise ValueError("password must contain at least 3 unique characters")
        return value


# ── Session Management Schemas ────────────────────────────────────────────

class SessionCreateRequest(_StrictRequestModel):
    session_id: str | None = None


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


class CheckpointRestoreRequest(_StrictRequestModel):
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


class ProviderRecoveryRequest(_StrictRequestModel):
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


@app.get("/aetheris_hero_video_graded.mp4")
async def serve_login_hero_video():
    """Serve the login HTML hero video."""
    video_path = Path(__file__).parent / "aetheris_hero_video_graded.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Hero video not found.")
    return FileResponse(video_path, media_type="video/mp4")


@app.post("/auth/register", status_code=201)
async def register_user(req: AuthRegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user, checking if the email already exists."""
    client_ip = request.client.host if request.client else "unknown"
    if not _enforce_auth_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts; slow down.",
        )

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


def _set_auth_cookie(response: JSONResponse, token: str) -> None:
    """HIGH-013: deliver the JWT via an httpOnly, SameSite=Strict cookie."""
    settings = get_settings()
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.ENVIRONMENT != "development",
        samesite="strict",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


@app.post("/auth/login")
async def login_user(req: AuthLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate credentials and emit an httpOnly JWT cookie."""
    client_ip = request.client.host if request.client else "unknown"
    if not _enforce_auth_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts; slow down.",
        )

    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": user.email})
    response = JSONResponse({"status": "ok"})
    _set_auth_cookie(response, token)
    return response


@app.post("/auth/logout")
async def logout_user() -> JSONResponse:
    """Clear the httpOnly auth cookie (HIGH-013)."""
    settings = get_settings()
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")
    return response


@app.post("/auth/refresh")
async def refresh_token(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Refresh the authenticated user's httpOnly JWT cookie."""
    token = create_access_token(data={"sub": current_user.email})
    response = JSONResponse({"status": "ok"})
    _set_auth_cookie(response, token)
    return response


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
            _aetheris["execution_manager"].execute(
                user_query=req.query.strip(),
                gateway=_gateway,
                strategy=_strategy,
                pool=_pool,
                history=history_list,
                passport=passport,
                decision_engine=_aetheris.get("decision_engine"),
                reasoning_graph=_aetheris.get("reasoning_graph"),
                claim_manager=_aetheris.get("claim_manager"),
                streaming_manager=_aetheris.get("streaming_manager"),
                conversation_director=_aetheris.get("conversation_director"),
                session_id=session_id,
            ),
            timeout=_PIPELINE_TIMEOUT_SEC,
        )

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
                "answer": "Pipeline execution failed.",
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

    session_id = str(uuid.uuid4())
    passport = create_request_passport(session_id=session_id)
    request_id = passport.request_id
    history_list = [msg.model_dump() for msg in req.history] if req.history else None

    try:
        _streaming_mgr.create_stream(request_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def _forward_pipeline_events():
        """Run the pipeline and forward its result into the StreamingManager.

        Routes through ``run_micro_mode``/``DecisionEngine`` — the same path
        as ``/api/query`` — so streaming and non-streaming requests share one
        execution path and telemetry contract (RFC-007 Step 1). Per-agent
        progress events are emitted internally by ``_run_with_decision_engine``
        via ``streaming_manager.emit(passport.request_id, ...)`` into this same
        ``_streaming_mgr``; this coroutine only needs to emit the terminal
        result/error event.
        """
        try:
            result = await asyncio.wait_for(
                _aetheris["execution_manager"].execute(
                    user_query=req.query.strip(),
                    gateway=_gateway,
                    strategy=_strategy,
                    pool=_pool,
                    history=history_list,
                    passport=passport,
                    decision_engine=_aetheris.get("decision_engine"),
                    reasoning_graph=_aetheris.get("reasoning_graph"),
                    claim_manager=_aetheris.get("claim_manager"),
                    streaming_manager=_streaming_mgr,
                    conversation_director=_aetheris.get("conversation_director"),
                    session_id=session_id,
                ),
                timeout=_PIPELINE_TIMEOUT_SEC,
            )
            await _streaming_mgr.emit(
                request_id,
                EventType.RESULT,
                {"payload": _build_frontend_payload(result)},
            )
        except asyncio.TimeoutError:
            await _streaming_mgr.emit(
                request_id,
                EventType.ERROR,
                {
                    "stage": "timeout",
                    "message": f"Pipeline timed out after {_PIPELINE_TIMEOUT_SEC}s.",
                },
            )
        except asyncio.CancelledError:
            logger.info("Pipeline forwarder cancelled for request_id=%s.", request_id)
            raise
        except Exception as exc:
            logger.exception("Pipeline forwarder error: %s", exc)
            await _streaming_mgr.emit(
                request_id,
                EventType.ERROR,
                {"stage": "unknown", "message": "Pipeline execution failed."},
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
            raise
        except Exception as exc:
            logger.exception("SSE stream error: %s", exc)
            error_event = {
                "event": "error",
                "data": {"stage": "unknown", "message": "Streaming failed."},
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


def _clean_model_name(model_str: str) -> str:
    """Format an OpenRouter/Gateway model identifier into a crisp display name."""
    parts = model_str.split("/")
    base = parts[-1]
    replacements = {
        "claude-3.5-sonnet": "claude-3.5-sonnet",
        "llama-3.3-70b-versatile": "llama-3.3-70b",
        "meta-llama-3.1-70b-instruct": "llama-3.1-70b",
        "llama-3.1-8b-instant": "llama-3.1-8b",
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.5-pro": "gemini-2.5-pro",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4o": "gpt-4o",
        "deepseek-chat": "deepseek-chat",
    }
    return replacements.get(base, base)


def _get_dynamic_models() -> list[dict[str, Any]]:
    """Return dynamic model list with health status and latency from active strategy."""
    if not _strategy:
        return []

    models_dict: dict[str, dict[str, Any]] = {}
    for role in _strategy.supported_roles:
        for model_str in _strategy.get_configured_model_chain(role):
            if model_str not in models_dict:
                provider_key = extract_provider_key(model_str)
                latency_str = "1.1s"
                is_active = _strategy.is_model_enabled(model_str)
                if _pool:
                    metrics = _pool.get_health_metrics(provider_key)
                    if metrics and metrics.mean_latency_ms > 0:
                        latency_str = f"{(metrics.mean_latency_ms / 1000.0):.1f}s"
                    state = _pool._providers.get(provider_key)
                    if state:
                        is_active = (
                            is_active
                            and state.is_available
                            and state.status.value != "dead"
                        )

                clean_name = _clean_model_name(model_str)
                models_dict[model_str] = {
                    "id": clean_name.replace(".", "").replace("-", ""),
                    "name": clean_name,
                    "full_id": model_str,
                    "provider": provider_key,
                    "latency": latency_str,
                    "active": is_active,
                    "roles": [role],
                }
            else:
                if role not in models_dict[model_str]["roles"]:
                    models_dict[model_str]["roles"].append(role)
    return list(models_dict.values())


@app.get("/api/status")
async def get_status(current_user: User = Depends(get_current_user)) -> dict:
    """Return provider health, dynamic models, and session telemetry."""
    return {
        "user": {"email": current_user.email, "role": current_user.role},
        "providers": _pool.get_all_statuses() if _pool else [],
        "models": _get_dynamic_models(),
        "telemetry": observer.get_telemetry_dict(),
        "mode": _strategy.mode.value if _strategy else "UNKNOWN",
    }


@app.get("/api/models")
async def get_models(current_user: User = Depends(get_current_user)) -> dict:
    """Return active models configured in the orchestrator strategy."""
    return {"models": _get_dynamic_models()}


class ModelAddRequest(_StrictRequestModel):
    model: str
    role: str = "generation"


class ModelToggleRequest(_StrictRequestModel):
    id: str
    active: bool


class StrategyModeRequest(_StrictRequestModel):
    mode: str


@app.post("/api/models/add")
async def add_model_endpoint(
    req: ModelAddRequest,
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Dynamically register a new model in the active strategy and pool."""
    if not _strategy or not _pool:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized.")
    model_str = req.model.strip()
    if not model_str:
        raise HTTPException(status_code=400, detail="Model identifier cannot be empty.")
    _strategy.add_model(model_str, req.role)
    provider_key = extract_provider_key(model_str)
    _pool.register_provider(provider_key, roles=[req.role])
    return {"status": "success", "models": _get_dynamic_models()}


@app.post("/api/models/toggle")
async def toggle_model_endpoint(
    req: ModelToggleRequest,
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Enable or disable a model provider in the active pool."""
    if not _pool:
        raise HTTPException(status_code=503, detail="ProviderPool not initialized.")
    model = next((item for item in _get_dynamic_models() if item["full_id"] == req.id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    if not _strategy or not _strategy.set_model_enabled(req.id, req.active):
        raise HTTPException(status_code=404, detail="Model not found.")
    return {"status": "success", "models": _get_dynamic_models()}


@app.post("/api/strategy/mode")
async def set_strategy_mode_endpoint(
    req: StrategyModeRequest,
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Switch the orchestrator strategy mode (FREE, HYBRID, PAID)."""
    if not _strategy or not _pool:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized.")
    try:
        _strategy.set_mode(req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "success", "mode": _strategy.mode.value}


class ConversationSaveRequest(_StrictRequestModel):
    id: str
    title: str = "New Conversation"
    mode: str = "HYBRID"
    transcript: list[dict[str, Any]] = PField(default_factory=list)


@app.get("/api/conversations")
async def get_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all conversation sessions owned by the current user from PostgreSQL."""
    stmt = (
        select(ConversationSessionRecord)
        .where(ConversationSessionRecord.owner_email == current_user.email)
        .options(selectinload(ConversationSessionRecord.messages))
        .order_by(ConversationSessionRecord.created_at.desc())
    )
    res = await db.execute(stmt)
    sessions = res.scalars().all()

    convs = []
    for s in sessions:
        sorted_msgs = sorted(s.messages, key=lambda m: m.timestamp)
        convs.append({
            "id": s.session_id,
            "title": s.title or "Conversation",
            "time": s.created_at.strftime("%b %d, %H:%M") if s.created_at else "Just now",
            "mode": s.state,
            "agentsCount": 1,
            "score": None,
            "transcript": [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "text": m.content,
                }
                for m in sorted_msgs
            ],
        })
    return {"conversations": convs}


@app.post("/api/conversations")
async def save_conversation(
    req: ConversationSaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Persist or update a conversation session and its transcript in PostgreSQL."""
    stmt = (
        select(ConversationSessionRecord)
        .where(
            ConversationSessionRecord.session_id == req.id,
            ConversationSessionRecord.owner_email == current_user.email,
        )
        .options(selectinload(ConversationSessionRecord.messages))
    )
    res = await db.execute(stmt)
    session_rec = res.scalars().first()

    if session_rec is None:
        session_rec = ConversationSessionRecord(
            session_id=req.id,
            owner_email=current_user.email,
            title=req.title[:255],
            state=req.mode[:32],
        )
        db.add(session_rec)
        await db.flush()
    else:
        session_rec.title = req.title[:255]
        session_rec.state = req.mode[:32]
        session_rec.turn_count = len(req.transcript)
        await db.execute(
            delete(ConversationMessageRecord).where(
                ConversationMessageRecord.session_id == session_rec.id
            )
        )

    for turn in req.transcript:
        msg_text = turn.get("text") or ""
        msg_role = turn.get("role") or "user"
        msg_rec = ConversationMessageRecord(
            session_id=session_rec.id,
            role=msg_role[:16],
            content=msg_text,
        )
        db.add(msg_rec)

    session_rec.turn_count = len(req.transcript)
    await db.commit()
    return {"status": "ok", "id": req.id}


@app.delete("/api/conversations/{session_id}")
async def delete_conversation(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a conversation owned by current user from PostgreSQL."""
    stmt = select(ConversationSessionRecord).where(
        ConversationSessionRecord.session_id == session_id,
        ConversationSessionRecord.owner_email == current_user.email,
    )
    res = await db.execute(stmt)
    session_rec = res.scalars().first()
    if session_rec:
        await db.delete(session_rec)
        await db.commit()
    return {"status": "deleted"}


def _get_vault_status() -> list[dict[str, Any]]:
    """Return secure masked status of API keys for each provider."""
    providers_meta = [
        {"account": "OPENROUTER_API_KEY", "name": "OpenRouter", "description": "Unified gateway for Anthropic, Llama, DeepSeek & Qwen models"},  # noqa: E501
        {"account": "OPENAI_API_KEY", "name": "OpenAI", "description": "GPT-4o, GPT-4o-mini, and Reasoning models"},  # noqa: E501
        {"account": "GOOGLE_API_KEY", "name": "Google AI Studio", "description": "Gemini 2.5 Flash, Gemini 2.5 Pro"},  # noqa: E501
        {"account": "GROQ_API_KEY", "name": "Groq Cloud", "description": "Ultra-fast Llama 3.3 70B & Llama 3.1 8B inference"},  # noqa: E501
        {"account": "NVIDIA_NIM_API_KEY", "name": "NVIDIA NIM", "description": "Enterprise Nemotron & Llama 405B inference"},  # noqa: E501
        {"account": "MISTRAL_API_KEY", "name": "Mistral AI", "description": "Mistral Large & Codestral models"},  # noqa: E501
        {"account": "CUSTOM_GATEWAY_KEY", "name": "Custom API Gateway", "description": "Custom endpoint or Local LLM (Ollama / vLLM / LiteLLM)"},  # noqa: E501
    ]
    results = []
    for p in providers_meta:
        env_var = f"AETHERIS_{p['account']}" if not p['account'].startswith("AETHERIS_") else p['account']
        val = os.environ.get(env_var, "") or os.environ.get(p["account"], "")
        has_key = bool(val and len(val.strip()) > 4)
        masked = f"••••••••••••{val.strip()[-4:]}" if has_key else "Not Configured"
        results.append({
            "account": p["account"],
            "name": p["name"],
            "description": p["description"],
            "configured": has_key,
            "masked": masked,
        })
    return results


class VaultSaveRequest(_StrictRequestModel):
    account: str
    secret: str


class CustomModelRequest(_StrictRequestModel):
    model_id: str
    role: str = "generation"


@app.get("/api/config/vault")
async def get_vault_status(current_user: User = Depends(get_current_user)) -> dict:
    """Return secure masked status of provider API keys in vault."""
    return {"providers": _get_vault_status()}


@app.post("/api/config/vault")
async def save_vault_secret(
    req: VaultSaveRequest,
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Save an API key securely into OS Keyring and running memory enclave."""
    account = req.account.strip()
    secret = req.secret.strip()
    allowed_accounts = {
        "OPENROUTER_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
        "GROQ_API_KEY", "NVIDIA_NIM_API_KEY", "MISTRAL_API_KEY",
        "CUSTOM_GATEWAY_KEY", "GITHUB_TOKEN",
    }
    if account not in allowed_accounts:
        raise HTTPException(status_code=400, detail="Invalid account identifier.")
    if secret:
        os.environ[f"AETHERIS_{account}"] = secret
        os.environ[account] = secret
        storage = "memory"
        try:
            import keyring
            keyring.set_password("Aetheris", account, secret)
            storage = "keyring"
        except Exception as exc:
            logger.debug("OS Keyring unavailable or non-writable: %s", exc)
    return {
        "status": "success",
        "storage": storage if secret else "unchanged",
        "providers": _get_vault_status(),
    }


@app.post("/api/models/custom")
async def register_custom_model(
    req: CustomModelRequest,
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Register a custom model and optional gateway URL in orchestrator."""
    if not _strategy or not _pool:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized.")
    model_str = req.model_id.strip()
    if not model_str:
        raise HTTPException(status_code=400, detail="Model ID cannot be empty.")
    _strategy.add_model(model_str, req.role)
    provider_key = extract_provider_key(model_str)
    _pool.register_provider(provider_key, roles=[req.role])
    return {"status": "success", "models": _get_dynamic_models()}


@app.get("/api/telemetry")
async def get_telemetry(current_user: User = Depends(get_current_user)) -> dict:
    """Return session telemetry metrics."""
    return observer.get_telemetry_dict()


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
    """Create a new conversation session owned by the caller (HIGH-015)."""
    import uuid

    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    session_id = req.session_id or str(uuid.uuid4())
    owner = current_user.email

    try:
        session = conversation_director.create_session(session_id, owner_email=owner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SessionCreateResponse(
        session_id=session.session_id,
        state=session.state.value,
        created_at=session.created_at.isoformat(),
    )


def _require_session_ownership(
    conversation_director: Any,
    session_id: str,
    current_user: User,
) -> None:
    """HIGH-015: reject cross-user session access with 403."""
    if not conversation_director.verify_access(session_id, current_user.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to the authenticated user.",
        )


@app.get("/api/sessions/{session_id}", response_model=SessionMetadataResponse)
async def get_session_metadata(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> SessionMetadataResponse:
    """Retrieve session metadata (HIGH-015 ownership enforced)."""
    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    _require_session_ownership(conversation_director, session_id, current_user)

    try:
        metadata = conversation_director.get_metadata(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SessionMetadataResponse(**metadata)


@app.get("/api/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> SessionHistoryResponse:
    """Retrieve conversation history (HIGH-015 ownership enforced)."""
    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    _require_session_ownership(conversation_director, session_id, current_user)

    try:
        history = conversation_director.get_history(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SessionHistoryResponse(history=history)


@app.delete("/api/sessions/{session_id}", response_model=SessionCloseResponse)
async def close_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> SessionCloseResponse:
    """Explicitly close a conversation session (HIGH-015 ownership enforced)."""
    from datetime import datetime

    conversation_director = _aetheris.get("conversation_director")
    if not conversation_director:
        raise HTTPException(status_code=503, detail="Conversation director not available")

    _require_session_ownership(conversation_director, session_id, current_user)

    try:
        conversation_director.transition_state(session_id, ConversationState.COMPLETED)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        checkpoints = await checkpoint_manager.list_checkpoints(
            request_id=request_id, user_email=current_user.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        checkpoint = await checkpoint_manager.restore_checkpoint(
            checkpoint_id, user_email=current_user.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        deleted_count = await checkpoint_manager.delete_checkpoints(
            request_id, user_email=current_user.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CheckpointDeleteResponse(
        request_id=request_id,
        deleted_count=deleted_count,
    )


# ── Execution Replay Debug Endpoint (Step 20a) ────────────────────────────

@app.get("/api/debug/replay/{trace_id}")
async def get_replay_trace(
    trace_id: str,
    current_user: User = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Return a recorded execution trace for offline replay/debugging.

    Gated by ``AETHERIS_ENABLE_REPLAY`` — when the flag is off the
    ``replay_store`` component is ``None`` and this reports 503 rather
    than fabricating an empty trace (ADR-007).
    """
    replay_store = _aetheris.get("replay_store")
    if not replay_store:
        raise HTTPException(status_code=503, detail="Execution replay is disabled")

    trace = replay_store.load(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Replay trace {trace_id} not found or expired")

    return trace.model_dump(mode="json")


@app.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus text exposition of decision and provider-health metrics.

    Auth: a scraper cannot present the httpOnly JWT cookie the admin endpoints
    rely on, so this path uses its own bearer token (``AETHERIS_METRICS_TOKEN``).
    In production the token is mandatory — an unset token means the endpoint
    refuses to serve rather than silently exposing internals. Outside production
    an unset token leaves it open so local scraping needs no setup.
    """
    settings = get_settings()
    expected = settings.METRICS_TOKEN

    if not expected:
        if settings.ENVIRONMENT == "production":
            logger.error("AETHERIS_METRICS_TOKEN unset — refusing to serve /metrics.")
            raise HTTPException(
                status_code=503,
                detail="Metrics endpoint unconfigured: set AETHERIS_METRICS_TOKEN.",
            )
    else:
        header = request.headers.get("authorization", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(presented, expected):
            raise HTTPException(status_code=401, detail="Invalid metrics token.")

    metrics.refresh(
        decision_engine=_aetheris.get("decision_engine"),
        pool=_pool,
    )
    return Response(content=metrics.render(), media_type=metrics.CONTENT_TYPE)


# ── Provider Health Monitoring Endpoints ──────────────────────────────────

@app.get("/api/providers/health", response_model=list[ProviderHealthResponse])
async def get_providers_health(
    current_user: User = Depends(require_role("admin")),
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
    current_user: User = Depends(require_role("admin")),
) -> ProviderRecoveryResponse:
    """Manually trigger recovery for a DEAD provider (admin only — MED-023)."""
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

@app.api_route("/{full_path:path}", methods=["GET"])
async def catch_all(full_path: str):
    """Catch-all route for SPA client-side routing."""
    # Skip API routes and auth routes
    if full_path.startswith("api/") or full_path.startswith("auth/") or full_path == "login":
        raise HTTPException(status_code=404, detail="Not found")

    # Check if the requested file exists in WEB_DIR (e.g., favicon.svg)
    import mimetypes
    web_dir_resolved = WEB_DIR.resolve()
    requested_file = (WEB_DIR / full_path).resolve()
    if requested_file.is_relative_to(web_dir_resolved) and requested_file.is_file():
        media_type, _ = mimetypes.guess_type(str(requested_file))
        return FileResponse(requested_file, media_type=media_type)

    # If it's a request for a static asset that doesn't exist, return 404
    if "." in full_path.split("/")[-1]:
        raise HTTPException(status_code=404, detail="Asset not found")

    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found.")
    return FileResponse(index, media_type="text/html")
