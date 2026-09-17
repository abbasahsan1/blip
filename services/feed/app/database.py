import logging
from blipp_common.database import get_db_pool

logger = logging.getLogger("feed-service.database")

FEED_SCHEMA_SQL = """
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
    author_avatar_url TEXT,
    -- T30: Soft-delete for content takedowns. NULL = active; NOT NULL = taken down.
    -- Feed queries MUST filter WHERE taken_down_at IS NULL.
    taken_down_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_feed_items_created_at ON feed_items (created_at DESC, blipp_id DESC) WHERE taken_down_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_feed_items_creator_id ON feed_items (creator_id) WHERE taken_down_at IS NULL;
-- Separate index for the taken_down_at column for efficient soft-delete filtering
CREATE INDEX IF NOT EXISTS idx_feed_items_taken_down ON feed_items (taken_down_at) WHERE taken_down_at IS NOT NULL;

-- T30: ALTER to add column on existing tables (safe for both fresh and existing deployments)
ALTER TABLE feed_items ADD COLUMN IF NOT EXISTS taken_down_at TIMESTAMP WITH TIME ZONE;

-- Engagement read projections
CREATE TABLE IF NOT EXISTS feed_item_stats (
    blipp_id UUID PRIMARY KEY,
    likes_count INTEGER NOT NULL DEFAULT 0,
    -- T24: saves_count for idempotent save projection counter
    saves_count INTEGER NOT NULL DEFAULT 0
);
ALTER TABLE feed_item_stats ADD COLUMN IF NOT EXISTS saves_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS user_likes_projection (
    user_id UUID NOT NULL,
    blipp_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, blipp_id)
);
CREATE INDEX IF NOT EXISTS idx_user_likes_proj_user ON user_likes_projection (user_id);

CREATE TABLE IF NOT EXISTS user_saves_projection (
    user_id UUID NOT NULL,
    blipp_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, blipp_id)
);
CREATE INDEX IF NOT EXISTS idx_user_saves_proj_user ON user_saves_projection (user_id);

CREATE TABLE IF NOT EXISTS user_follows_projection (
    follower_id UUID NOT NULL,
    followee_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (follower_id, followee_id)
);
CREATE INDEX IF NOT EXISTS idx_user_follows_proj_follower ON user_follows_projection (follower_id);
"""


async def init_feed_db() -> None:
    """Initializes the isolated database schema and CQRS engagement projections for Feed."""
    pool = await get_db_pool()
    if not pool:
        raise RuntimeError("Database pool unavailable for Feed Service initialization")
    async with pool.acquire() as conn:
        await conn.execute(FEED_SCHEMA_SQL)
        logger.info("Executed Feed Service isolated schema DDL")
