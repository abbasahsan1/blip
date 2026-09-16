import asyncio
import logging
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from blipp_common.config import BaseCommonSettings

logger = logging.getLogger("blipp_common.database")


# ─── Unified SQLAlchemy Declarative Base ──────────────────────────────────────

class Base(DeclarativeBase):
    """Unified SQLAlchemy Declarative Base for all Blipp domain entities."""
    pass


# ─── Async SQLAlchemy Engine & Session Factory ────────────────────────────────

_async_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine(settings: Optional[BaseCommonSettings] = None) -> AsyncEngine:
    """
    Returns the singleton AsyncEngine configured with robust production defaults.
    - pool_pre_ping=True prevents stale connections across workers.
    - pool_size=10 with max_overflow=20 handles high concurrent bursts.
    """
    global _async_engine, _session_factory
    if _async_engine is None:
        cfg = settings or BaseCommonSettings()
        _async_engine = create_async_engine(
            cfg.async_database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
        _session_factory = async_sessionmaker(
            bind=_async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info(f"Initialized async SQLAlchemy engine for {cfg.POSTGRES_HOST}:{cfg.POSTGRES_PORT}/{cfg.POSTGRES_DB}")
    return _async_engine


def get_session_factory(settings: Optional[BaseCommonSettings] = None) -> async_sessionmaker[AsyncSession]:
    """Returns the async session factory."""
    global _session_factory
    if _session_factory is None:
        get_async_engine(settings)
    return _session_factory  # type: ignore


@asynccontextmanager
async def get_db_session(settings: Optional[BaseCommonSettings] = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager providing a scoped database session with automatic commit / rollback.
    Prevents dangling transactions during batch worker lifecycles.
    """
    factory = get_session_factory(settings)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db(settings: Optional[BaseCommonSettings] = None) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with get_db_session(settings) as session:
        yield session


# ─── Shared asyncpg High-Performance Connection Pool ─────────────────────────

_asyncpg_pool: Optional[asyncpg.Pool] = None


async def get_db_pool(settings: Optional[BaseCommonSettings] = None) -> asyncpg.Pool:
    """Returns the singleton asyncpg connection pool, re-initializing if event loop changed."""
    global _asyncpg_pool
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _asyncpg_pool is not None:
        pool_loop = getattr(_asyncpg_pool, "_loop", None)
        if pool_loop and (pool_loop.is_closed() or (current_loop and pool_loop != current_loop)):
            _asyncpg_pool = None

    if _asyncpg_pool is None:
        await init_db_pool(settings)
    return _asyncpg_pool  # type: ignore


async def init_db_pool(settings: Optional[BaseCommonSettings] = None) -> asyncpg.Pool:
    """Initializes the asyncpg connection pool for the configured service database."""
    global _asyncpg_pool
    if _asyncpg_pool is not None:
        return _asyncpg_pool

    cfg = settings or BaseCommonSettings()
    db_name = cfg.POSTGRES_DB

    logger.info(f"Connecting asyncpg pool to {cfg.POSTGRES_HOST}:{cfg.POSTGRES_PORT}/{db_name}")
    try:
        _asyncpg_pool = await asyncpg.create_pool(
            host=cfg.POSTGRES_HOST,
            port=cfg.POSTGRES_PORT,
            user=cfg.POSTGRES_USER,
            password=cfg.POSTGRES_PASSWORD,
            database=db_name,
            min_size=2,
            max_size=20,
            timeout=10.0,
        )
        logger.info(f"Connected asyncpg pool to '{db_name}'")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL db '{db_name}': {e}")
        raise RuntimeError(f"Could not establish asyncpg connection pool to PostgreSQL database '{db_name}': {e}")

    return _asyncpg_pool


async def close_db_pool() -> None:
    """Closes the asyncpg pool and SQLAlchemy engine gracefully."""
    global _asyncpg_pool, _async_engine, _session_factory
    if _asyncpg_pool is not None:
        try:
            await _asyncpg_pool.close()
        except Exception as e:
            logger.warning(f"Error closing asyncpg pool: {e}")
        _asyncpg_pool = None
        logger.info("Closed asyncpg connection pool")

    if _async_engine is not None:
        try:
            await _async_engine.dispose()
        except Exception as e:
            logger.warning(f"Error disposing SQLAlchemy engine: {e}")
        _async_engine = None
        _session_factory = None
        logger.info("Disposed SQLAlchemy async engine")


# Monolithic schema removed: each service strictly owns and initializes its own domain tables.
CREATE_TABLES_SQL = ""


# Aliases for backward compatibility
init_db = init_db_pool
close_db = close_db_pool

__all__ = [
    "Base",
    "get_async_engine",
    "get_session_factory",
    "get_db_session",
    "get_db",
    "get_db_pool",
    "init_db_pool",
    "close_db_pool",
    "init_db",
    "close_db",
    "CREATE_TABLES_SQL",
]
