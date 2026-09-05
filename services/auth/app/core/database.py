import logging
import asyncpg
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("auth-service.database")

_pool: Optional[asyncpg.Pool] = None

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS blipps (
    blipp_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    audio_url TEXT NOT NULL,
    audio_variants JSONB NOT NULL DEFAULT '{}'::jsonb,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'published',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blipps_status_created ON blipps (status, created_at DESC);

CREATE TABLE IF NOT EXISTS users_profile (
    user_id UUID PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    bio TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_profile_username ON users_profile (username);
"""


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        await init_db()
    return _pool


async def init_db() -> None:
    global _pool
    if _pool is not None:
        return

    candidate_databases = [settings.POSTGRES_DB, "keycloak", "postgres"]
    connected = False

    for db_name in candidate_databases:
        try:
            logger.info(f"Connecting to PostgreSQL at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{db_name}")
            _pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=db_name,
                min_size=1,
                max_size=10,
                timeout=10.0,
            )
            connected = True
            logger.info(f"PostgreSQL connection pool initialized on database '{db_name}'")
            break
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL database '{db_name}': {e}")

    if not connected or _pool is None:
        logger.error("Could not establish PostgreSQL connection pool to any candidate database")
        return

    async with _pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
        logger.info("Verified/created 'blipps' schema successfully")


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")
