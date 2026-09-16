import logging
from blipp_common.database import get_db_pool

logger = logging.getLogger("messaging.database")

MESSAGING_SCHEMA_SQL = """
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
"""


async def init_messaging_db() -> None:
    """Initializes the database schema for Messaging Service."""
    pool = await get_db_pool()
    if not pool:
        raise RuntimeError("Database pool unavailable for Messaging Service initialization")
    async with pool.acquire() as conn:
        await conn.execute(MESSAGING_SCHEMA_SQL)
        logger.info("Executed Messaging Service isolated schema DDL")
