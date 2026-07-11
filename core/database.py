"""
Database configuration using SQLAlchemy (async) and asyncpg.
Provides async engine, sessionmaker, Base declarative class, and dependency injection helper.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings

settings = get_settings()

# HIGH-016 audit fix: database SSL is now configurable via ``DATABASE_SSL``
# environment variable.  Default ``False`` keeps local development friction
# free; production deployments must set this to ``True`` so the underlying
# asyncpg driver negotiates an encrypted channel.
def get_engine_kwargs(db_url: str) -> dict:
    kwargs = {"echo": False}
    if db_url.startswith("postgresql"):
        kwargs.update({
            "pool_size": 20,
            "max_overflow": 10,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "connect_args": {"ssl": settings.DATABASE_SSL},
        })
    return kwargs

engine = create_async_engine(
    settings.DATABASE_URL,
    **get_engine_kwargs(settings.DATABASE_URL),
)

async_session_maker = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)

def rebind_engine(new_url: str):
    """Rebind the engine and session maker to a new database URL (e.g. SQLite fallback)."""
    global engine, async_session_maker
    engine = create_async_engine(new_url, **get_engine_kwargs(new_url))
    async_session_maker = async_sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

# Modern Declarative Base class (SQLAlchemy 2.0 style)
class Base(DeclarativeBase):
    pass

# FastAPI Dependency for obtaining an async session per request
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an asynchronous database session.
    The session is automatically closed when the request block finishes.
    """
    session = async_session_maker()
    try:
        yield session
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            await session.close()
        except Exception:
            pass
