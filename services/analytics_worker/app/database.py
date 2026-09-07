import uuid
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone, date
import asyncpg

from app.config import settings

logger = logging.getLogger("analytics-worker.database")

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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

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

    candidate_databases = [settings.POSTGRES_DB, "blipp", "keycloak", "postgres"]
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
                max_size=5,
                timeout=10.0,
            )
            connected = True
            logger.info(f"PostgreSQL connection pool initialized on database '{db_name}'")
            break
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL database '{db_name}': {e}")

    if not connected or _pool is None:
        raise RuntimeError("Could not establish PostgreSQL connection pool")

    async with _pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
        logger.info("Verified/created analytics tables in database")


async def record_playback_engagement(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    blipp_id: uuid.UUID,
    position_seconds: float,
    duration_seconds: float,
    event_type: str,
    device_signal: str,
    timestamp_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Applies Section 6.5 aggregation business logic atomically:
    1. Treats background listening ('screen_off', 'bluetooth_connected', 'app_backgrounded')
       as active playback engagement.
    2. Aggregates total_seconds_listened and drop_off_position_seconds.
    3. Checks completion threshold (>= 0.9 * duration).
    4. Increments CreatorMinutesAgg.total_minutes_listened for the blipp's creator.
    """
    pool = await get_db_pool()

    # Determine session date
    session_date = date.today()
    if timestamp_str:
        try:
            session_date = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).date()
        except Exception:
            session_date = date.today()

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Guarantee user profile row exists to satisfy foreign key
            await conn.execute(
                """
                INSERT INTO users_profile (user_id, username, display_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
                str(user_id),
                "Listener",
            )

            # 2. Lookup blipp details (creator_id, official duration)
            blipp_row = await conn.fetchrow(
                """
                SELECT creator_id, duration_seconds
                FROM blipps
                WHERE blipp_id = $1
                """,
                blipp_id,
            )

            if not blipp_row:
                logger.warning(f"Blipp {blipp_id} not found in database. Skipping engagement event.")
                return None

            creator_id = blipp_row["creator_id"]
            effective_duration = float(blipp_row["duration_seconds"]) if blipp_row["duration_seconds"] else float(duration_seconds)
            effective_duration = max(effective_duration, 1.0)

            # 3. Lookup existing session
            existing_session = await conn.fetchrow(
                """
                SELECT total_seconds_listened, completed, drop_off_position_seconds
                FROM listening_session_agg
                WHERE session_id = $1
                """,
                session_id,
            )

            prev_seconds = float(existing_session["total_seconds_listened"]) if existing_session else 0.0
            was_completed = bool(existing_session["completed"]) if existing_session else False

            # Calculate new seconds listened
            current_pos = max(0.0, float(position_seconds))
            if event_type == "play_complete":
                new_seconds = max(prev_seconds, effective_duration)
                is_completed = True
                drop_off = None
            elif event_type == "skip":
                new_seconds = max(prev_seconds, current_pos)
                is_completed = was_completed or (new_seconds >= 0.9 * effective_duration)
                drop_off = current_pos
            else:
                # Normal play_progress event (including active screen_off / bluetooth signals)
                new_seconds = max(prev_seconds, current_pos)
                is_completed = was_completed or (new_seconds >= 0.9 * effective_duration)
                drop_off = current_pos

            delta_seconds = max(0.0, new_seconds - prev_seconds)

            # 4. Upsert ListeningSessionAgg
            await conn.execute(
                """
                INSERT INTO listening_session_agg (
                    session_id, user_id, blipp_id, total_seconds_listened, completed, drop_off_position_seconds, session_date
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (session_id) DO UPDATE SET
                    total_seconds_listened = EXCLUDED.total_seconds_listened,
                    completed = listening_session_agg.completed OR EXCLUDED.completed,
                    drop_off_position_seconds = EXCLUDED.drop_off_position_seconds,
                    session_date = EXCLUDED.session_date
                """,
                session_id,
                user_id,
                blipp_id,
                new_seconds,
                is_completed,
                drop_off,
                session_date,
            )

            # 5. Upsert CreatorMinutesAgg if incremental seconds > 0 and creator known
            delta_minutes = delta_seconds / 60.0
            if creator_id and delta_minutes > 0.0:
                await conn.execute(
                    """
                    INSERT INTO creator_minutes_agg (
                        id, creator_id, blipp_id, total_minutes_listened, date
                    ) VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (creator_id, blipp_id, date) DO UPDATE SET
                        total_minutes_listened = creator_minutes_agg.total_minutes_listened + EXCLUDED.total_minutes_listened
                    """,
                    uuid.uuid4(),
                    creator_id,
                    blipp_id,
                    delta_minutes,
                    session_date,
                )

            return {
                "session_id": session_id,
                "user_id": user_id,
                "blipp_id": blipp_id,
                "creator_id": creator_id,
                "total_seconds_listened": new_seconds,
                "delta_seconds": delta_seconds,
                "delta_minutes": delta_minutes,
                "completed": is_completed,
                "drop_off_position_seconds": drop_off,
            }


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")
