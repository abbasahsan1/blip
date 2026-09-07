import logging
from typing import AsyncGenerator
import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from blipp_common.database import (
    Base,
    get_async_engine,
    get_session_factory,
    get_db_session,
    get_db,
    get_db_pool as _common_get_db_pool,
    init_db_pool as _common_init_db_pool,
    close_db_pool as _common_close_db_pool,
    CREATE_TABLES_SQL,
)
from app.core.config import settings

logger = logging.getLogger("auth-service.database")


async def get_db_pool() -> asyncpg.Pool:
    """Returns the shared asyncpg connection pool initialized with auth settings."""
    return await _common_get_db_pool(settings)


async def init_db() -> None:
    """Initializes the database connection pool and applies unified table DDL."""
    await _common_init_db_pool(settings)


async def close_db() -> None:
    """Closes the asyncpg connection pool and disposes the SQLAlchemy engine."""
    await _common_close_db_pool()


__all__ = [
    "Base",
    "get_async_engine",
    "get_session_factory",
    "get_db_session",
    "get_db",
    "get_db_pool",
    "init_db",
    "close_db",
    "CREATE_TABLES_SQL",
]
