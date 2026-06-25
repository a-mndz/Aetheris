"""
Database configuration using SQLAlchemy (async) and asyncpg.
Provides async engine, sessionmaker, Base declarative class, and dependency injection helper.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from core.config import get_settings

settings = get_settings()

# Create async engine.
# For production safety and correctness:
# - pool_size determines the number of connections to keep inside the pool.
# - max_overflow determines how many connections can be opened beyond pool_size when needed.
# - pool_pre_ping checks the health of connections before checking them out to prevent stale connection errors.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Set to True only for debugging generated SQL in development
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"ssl": False},
)

# Create an async session maker.
# - expire_on_commit=False prevents SQLAlchemy from querying the database on expired attribute access after commit, which is crucial for async workflows.
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
