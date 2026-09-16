import logging
from blipp_common.database import get_db_pool

logger = logging.getLogger("moderation.database")

MODERATION_SCHEMA_SQL = """
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


async def init_moderation_db() -> None:
    """Initializes the database schema for Moderation Service."""
    pool = await get_db_pool()
    if not pool:
        raise RuntimeError("Database pool unavailable for Moderation Service initialization")
    async with pool.acquire() as conn:
        await conn.execute(MODERATION_SCHEMA_SQL)
        logger.info("Executed Moderation Service isolated schema DDL")
