import uuid
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone, date
import asyncpg

from blipp_common.database import (
    get_db_pool as _common_get_db_pool,
    init_db_pool as _common_init_db_pool,
    close_db_pool as _common_close_db_pool,
)
from app.config import settings

logger = logging.getLogger("analytics-worker.database")


async def get_db_pool() -> asyncpg.Pool:
    """Returns the shared asyncpg connection pool initialized with analytics worker settings."""
    return await _common_get_db_pool(settings)


async def init_db() -> None:
    """Initializes the database connection pool and applies unified table DDL."""
    await _common_init_db_pool(settings)


async def close_db() -> None:
    """Closes the asyncpg connection pool."""
    await _common_close_db_pool()


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


__all__ = [
    "get_db_pool",
    "init_db",
    "close_db",
    "record_playback_engagement",
]
