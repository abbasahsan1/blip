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
    """Initializes the asyncpg connection pool and ensures database schema DDL is applied."""
    global _asyncpg_pool
    if _asyncpg_pool is not None:
        return _asyncpg_pool

    cfg = settings or BaseCommonSettings()
    candidate_databases = [cfg.POSTGRES_DB, "blipp", "keycloak", "postgres"]

    for db_name in candidate_databases:
        try:
            logger.info(f"Connecting asyncpg to {cfg.POSTGRES_HOST}:{cfg.POSTGRES_PORT}/{db_name}")
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
            break
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL db '{db_name}': {e}")

    if _asyncpg_pool is None:
        raise RuntimeError("Could not establish asyncpg connection pool to PostgreSQL")

    # Apply standard tables DDL
    try:
        async with _asyncpg_pool.acquire() as conn:
            await conn.execute(CREATE_TABLES_SQL)
            logger.info("Executed unified database tables DDL")
    except Exception as e:
        logger.warning(f"Database DDL execution note: {e}")

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


# ─── Unified Database Tables DDL ─────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users_profile (
    user_id UUID PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    bio TEXT,
    avatar_url TEXT,
    is_creator BOOLEAN NOT NULL DEFAULT FALSE,
    verification_status VARCHAR(50) NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS is_creator BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) NOT NULL DEFAULT 'unverified';
ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'active';

CREATE INDEX IF NOT EXISTS idx_users_profile_username ON users_profile (username);
CREATE INDEX IF NOT EXISTS idx_users_profile_status ON users_profile (status);

CREATE TABLE IF NOT EXISTS follows (
    follower_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    followee_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_follower_followee UNIQUE (follower_id, followee_id)
);

CREATE INDEX IF NOT EXISTS idx_follows_follower_id ON follows (follower_id);
CREATE INDEX IF NOT EXISTS idx_follows_followee_id ON follows (followee_id);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    raw_file_url VARCHAR(1024) NOT NULL,
    upload_type VARCHAR(50) NOT NULL DEFAULT 'audio',
    processing_status VARCHAR(50) NOT NULL DEFAULT 'created',
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
CREATE INDEX IF NOT EXISTS idx_blipps_parent_upload_id ON blipps (parent_upload_id);

CREATE TABLE IF NOT EXISTS saves (
    user_id UUID NOT NULL,
    blipp_id UUID NOT NULL REFERENCES blipps(blipp_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_blipp_save UNIQUE (user_id, blipp_id),
    PRIMARY KEY (user_id, blipp_id)
);

CREATE INDEX IF NOT EXISTS idx_saves_user_id ON saves (user_id);
CREATE INDEX IF NOT EXISTS idx_saves_blipp_id ON saves (blipp_id);
CREATE INDEX IF NOT EXISTS idx_saves_created_at ON saves (created_at DESC);

CREATE TABLE IF NOT EXISTS likes (
    -- Likes are owned by Social Graph while blipps are owned by Content
    -- Ingest, so these deliberately do not use cross-service foreign keys.
    user_id UUID NOT NULL,
    blipp_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_blipp_like UNIQUE (user_id, blipp_id),
    PRIMARY KEY (user_id, blipp_id)
);

CREATE INDEX IF NOT EXISTS idx_likes_blipp_id ON likes (blipp_id);
CREATE INDEX IF NOT EXISTS idx_likes_created_at ON likes (created_at DESC);

CREATE TABLE IF NOT EXISTS feed_items (
    blipp_id UUID PRIMARY KEY,
    creator_id UUID NOT NULL,
    title VARCHAR(255),
    description TEXT,
    audio_url TEXT NOT NULL,
    audio_variants JSONB NOT NULL DEFAULT '{}'::jsonb,
    duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    author_username VARCHAR(255),
    author_display_name VARCHAR(255),
    author_avatar_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_feed_items_created_at ON feed_items (created_at DESC, blipp_id DESC);

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

CREATE TABLE IF NOT EXISTS dm_threads (
    thread_id UUID PRIMARY KEY,
    participant_ids UUID[] NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dm_threads_participants ON dm_threads USING GIN (participant_ids);

CREATE TABLE IF NOT EXISTS dm_messages (
    message_id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES dm_threads(thread_id) ON DELETE CASCADE,
    sender_id UUID NOT NULL,
    message_type VARCHAR(50) NOT NULL DEFAULT 'text',
    blipp_id UUID,
    body TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dm_messages_thread_id ON dm_messages (thread_id);
CREATE INDEX IF NOT EXISTS idx_dm_messages_sender_id ON dm_messages (sender_id);
CREATE INDEX IF NOT EXISTS idx_dm_messages_created_at ON dm_messages (created_at DESC);

CREATE TABLE IF NOT EXISTS stories (
    story_id UUID PRIMARY KEY,
    creator_id UUID NOT NULL,
    audio_url TEXT NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stories_creator_id ON stories (creator_id);
CREATE INDEX IF NOT EXISTS idx_stories_expires_at ON stories (expires_at);

CREATE TABLE IF NOT EXISTS reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id UUID NOT NULL,
    blipp_id UUID NOT NULL,
    creator_id UUID,
    reason VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reports_reporter_id ON reports (reporter_id);
CREATE INDEX IF NOT EXISTS idx_reports_blipp_id ON reports (blipp_id);
CREATE INDEX IF NOT EXISTS idx_reports_creator_id ON reports (creator_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports (status);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports (created_at DESC);

CREATE TABLE IF NOT EXISTS strikes (
    strike_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL,
    blipp_id UUID,
    reason VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_strikes_creator_id ON strikes (creator_id);
CREATE INDEX IF NOT EXISTS idx_strikes_created_at ON strikes (created_at DESC);
"""

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
