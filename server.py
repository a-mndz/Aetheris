"""
Aetheris — Adaptive Multi-Model Reasoning Orchestrator
Web Server: FastAPI backend serving the web UI and pipeline API.

Launch with:  python main.py --web
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
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
from core.security import hash_password, verify_password, create_access_token, get_current_user
from orchestrator import run_micro_mode, stream_micro_mode
from orchestrator.pipelines import _build_frontend_payload
from telemetry.observer import observer

logger = logging.getLogger("aetheris.web")

_PIPELINE_TIMEOUT_SEC = 900

# ── Global infrastructure (initialised in lifespan) ─────────────────────
_gateway: AsyncAPIGateway | None = None
_strategy: ProviderStrategy | None = None
_pool: ProviderPool | None = None


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
    global _gateway, _strategy, _pool

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

    _strategy = ProviderStrategy(mode="HYBRID")
    _pool = _bootstrap_pool(_strategy)
    _gateway = AsyncAPIGateway()

    logger.info(
        "Aetheris Web Server ready — mode=%s, providers=%d",
        _strategy.mode.value,
        len(_pool.get_all_statuses()) if _pool else 0,
    )
    yield

    if _gateway:
        await _gateway.close()
    observer.print_session_report()
    logger.info("Aetheris Web Server shut down.")


app = FastAPI(title="Aetheris", version="1.0.0", lifespan=lifespan)

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
        result = await asyncio.wait_for(
            run_micro_mode(
                user_query=req.query.strip(),
                gateway=_gateway,
                strategy=_strategy,
                pool=_pool,
                history=history_list,
            ),
            timeout=_PIPELINE_TIMEOUT_SEC,
        )

        return JSONResponse(_build_frontend_payload(result))

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

    history_list = [msg.model_dump() for msg in req.history] if req.history else None

    async def event_generator():
        try:
            async for event in stream_micro_mode(
                user_query=req.query.strip(),
                gateway=_gateway,
                strategy=_strategy,
                pool=_pool,
                history=history_list,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled by client.")
            return
        except Exception as exc:
            logger.exception("SSE stream error: %s", exc)
            error_event = {
                "event": "error",
                "stage": "unknown",
                "message": f"{type(exc).__name__}: {exc}",
            }
            yield f"data: {json.dumps(error_event)}\n\n"

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
