import logging
from blipp_common.database import get_db_pool
from blipp_common.outbox import OUTBOX_TABLE_SQL

logger = logging.getLogger("social-graph.database")

SOCIAL_GRAPH_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS users_profile (
    user_id UUID PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    bio TEXT,
    avatar_url TEXT,
    is_creator BOOLEAN NOT NULL DEFAULT FALSE,
    verification_status VARCHAR(50) NOT NULL DEFAULT 'unverified',
    status VARCHAR(50) NOT NULL DEFAULT 'active',
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
    CONSTRAINT uq_follower_followee UNIQUE (follower_id, followee_id),
    PRIMARY KEY (follower_id, followee_id)
);

CREATE INDEX IF NOT EXISTS idx_follows_follower_id ON follows (follower_id);
CREATE INDEX IF NOT EXISTS idx_follows_followee_id ON follows (followee_id);

CREATE TABLE IF NOT EXISTS likes (
    user_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    blipp_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_blipp_like UNIQUE (user_id, blipp_id),
    PRIMARY KEY (user_id, blipp_id)
);

CREATE INDEX IF NOT EXISTS idx_likes_blipp_id ON likes (blipp_id);
CREATE INDEX IF NOT EXISTS idx_likes_created_at ON likes (created_at DESC);

CREATE TABLE IF NOT EXISTS saves (
    user_id UUID NOT NULL REFERENCES users_profile(user_id) ON DELETE CASCADE,
    blipp_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_blipp_save UNIQUE (user_id, blipp_id),
    PRIMARY KEY (user_id, blipp_id)
);

CREATE INDEX IF NOT EXISTS idx_saves_user_id ON saves (user_id);
CREATE INDEX IF NOT EXISTS idx_saves_blipp_id ON saves (blipp_id);
CREATE INDEX IF NOT EXISTS idx_saves_created_at ON saves (created_at DESC);

{OUTBOX_TABLE_SQL}
"""


async def init_social_db() -> None:
    """Initializes the database schema for Social Graph."""
    pool = await get_db_pool()
    if not pool:
        raise RuntimeError("Database pool unavailable for Social Graph initialization")
    async with pool.acquire() as conn:
        await conn.execute(SOCIAL_GRAPH_SCHEMA_SQL)
        logger.info("Executed Social Graph isolated schema DDL")
