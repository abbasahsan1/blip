import logging
from blipp_common.database import get_db_pool
from blipp_common.outbox import OUTBOX_TABLE_SQL

logger = logging.getLogger("content-ingest.database")

CONTENT_INGEST_SCHEMA_SQL = f"""
-- Uploads table (Content Ingest boundary)
CREATE TABLE IF NOT EXISTS uploads (
    upload_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blipp_id UUID,
    creator_id UUID NOT NULL,
    raw_file_url VARCHAR(1024) NOT NULL,
    upload_type VARCHAR(50) NOT NULL DEFAULT 'audio',
    processing_status VARCHAR(50) NOT NULL DEFAULT 'created',
    title VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE uploads ADD COLUMN IF NOT EXISTS blipp_id UUID;

CREATE INDEX IF NOT EXISTS idx_uploads_creator_id ON uploads (creator_id);
CREATE INDEX IF NOT EXISTS idx_uploads_processing_status ON uploads (processing_status);

-- Blipps table (Published audio reels)
CREATE TABLE IF NOT EXISTS blipps (
    blipp_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL,
    title VARCHAR(255),
    description TEXT,
    audio_url TEXT NOT NULL,
    audio_variants JSONB NOT NULL DEFAULT '{{}}'::jsonb,
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

{OUTBOX_TABLE_SQL}
"""


async def init_ingest_db() -> None:
    """Initializes the database schema for Content Ingest."""
    pool = await get_db_pool()
    if not pool:
        raise RuntimeError("Database pool unavailable for Content Ingest initialization")
    async with pool.acquire() as conn:
        await conn.execute(CONTENT_INGEST_SCHEMA_SQL)
        logger.info("Executed Content Ingest isolated schema DDL")
