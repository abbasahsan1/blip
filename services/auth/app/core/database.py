import asyncio
import logging
import asyncpg
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("auth-service.database")

_pool: Optional[asyncpg.Pool] = None

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users_profile (
    user_id UUID PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    bio TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_profile_username ON users_profile (username);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    raw_file_url VARCHAR(1024) NOT NULL,
    upload_type VARCHAR(50) NOT NULL DEFAULT 'audio',
    processing_status VARCHAR(50) NOT NULL DEFAULT 'queued',
    title VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uploads_creator_id ON uploads (creator_id);
CREATE INDEX IF NOT EXISTS idx_uploads_processing_status ON uploads (processing_status);

CREATE TABLE IF NOT EXISTS blipps (
    blipp_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    title VARCHAR(255),
    description TEXT,
    audio_url TEXT NOT NULL,
    audio_variants JSONB NOT NULL DEFAULT '{}'::jsonb,
    duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    status VARCHAR(50) NOT NULL DEFAULT 'published',
    scheduled_at TIMESTAMP WITH TIME ZONE,
    source_type VARCHAR(50) NOT NULL DEFAULT 'direct_upload',
    parent_upload_id UUID REFERENCES uploads(upload_id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blipps_status_created ON blipps (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_blipps_creator_id ON blipps (creator_id);

ALTER TABLE blipps ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE blipps ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en';
ALTER TABLE blipps ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE blipps ADD COLUMN IF NOT EXISTS source_type VARCHAR(50) DEFAULT 'direct_upload';
ALTER TABLE blipps ADD COLUMN IF NOT EXISTS parent_upload_id UUID REFERENCES uploads(upload_id) ON DELETE SET NULL;
ALTER TABLE blipps ALTER COLUMN title DROP NOT NULL;
ALTER TABLE blipps ALTER COLUMN duration_seconds TYPE DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_blipps_parent_upload_id ON blipps (parent_upload_id);

CREATE TABLE IF NOT EXISTS listening_session_agg (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    blipp_id UUID NOT NULL REFERENCES blipps(blipp_id) ON DELETE CASCADE,
    total_seconds_listened DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    drop_off_position_seconds DOUBLE PRECISION,
    session_date DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_listening_session_user ON listening_session_agg (user_id, session_date DESC);
CREATE INDEX IF NOT EXISTS idx_listening_session_blipp ON listening_session_agg (blipp_id);

CREATE TABLE IF NOT EXISTS creator_minutes_agg (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    blipp_id UUID NOT NULL REFERENCES blipps(blipp_id) ON DELETE CASCADE,
    total_minutes_listened DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    CONSTRAINT uq_creator_blipp_date UNIQUE (creator_id, blipp_id, date)
);

CREATE INDEX IF NOT EXISTS idx_creator_minutes_creator_date ON creator_minutes_agg (creator_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_creator_minutes_blipp ON creator_minutes_agg (blipp_id);
"""


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _pool is not None:
        pool_loop = getattr(_pool, "_loop", None)
        if pool_loop and (pool_loop.is_closed() or (current_loop and pool_loop != current_loop)):
            _pool = None

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
