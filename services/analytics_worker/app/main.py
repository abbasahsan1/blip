import asyncio
import json
import logging
import signal
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

import httpx
import nats
from nats.aio.client import Client as NATSClient
from nats.js.api import RetentionPolicy, StorageType
from nats.js.client import JetStreamContext

from blipp_common.config import settings
from blipp_common.database import close_db, get_db_pool, init_db

NATS_CONSUMER_GROUP = "analytics-workers"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("analytics-worker")

_running = True
_http_client: Optional[httpx.AsyncClient] = None

ANALYTICS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analytics_blipp_metadata (
    blipp_id UUID PRIMARY KEY,
    creator_id UUID NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    title VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_analytics_meta_creator ON analytics_blipp_metadata (creator_id);

CREATE TABLE IF NOT EXISTS listening_session_agg (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    blipp_id UUID NOT NULL,
    total_seconds_listened DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    drop_off_position_seconds DOUBLE PRECISION,
    session_date DATE NOT NULL DEFAULT CURRENT_DATE
);
CREATE INDEX IF NOT EXISTS idx_listening_session_user ON listening_session_agg (user_id, session_date DESC);
CREATE INDEX IF NOT EXISTS idx_listening_session_blipp ON listening_session_agg (blipp_id);

CREATE TABLE IF NOT EXISTS creator_minutes_agg (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL,
    blipp_id UUID NOT NULL,
    total_minutes_listened DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    CONSTRAINT uq_creator_blipp_date UNIQUE (creator_id, blipp_id, date)
);
CREATE INDEX IF NOT EXISTS idx_creator_minutes_creator_date ON creator_minutes_agg (creator_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_creator_minutes_blipp ON creator_minutes_agg (blipp_id);
"""


def handle_shutdown(sig, frame):
    global _running
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    _running = False


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=3.0)
    return _http_client


async def init_analytics_db() -> None:
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        await conn.execute(ANALYTICS_SCHEMA_SQL)
        logger.info("Initialized Analytics isolated database schema")


async def record_playback_engagement(
    event_id: Optional[uuid.UUID],
    session_id: Optional[uuid.UUID],
    user_id: uuid.UUID,
    blipp_id: Optional[uuid.UUID],
    position_seconds: float,
    duration_seconds: float,
    event_type: str,
    device_signal: str,
    timestamp_str: Optional[str] = None,
    creator_id_fallback: Optional[uuid.UUID] = None,
) -> Optional[Dict[str, Any]]:
    """
    Applies Section 6.5 aggregation business logic using isolated analytics metadata projection.
    """
    pool = await get_db_pool(settings)

    session_date = date.today()
    if timestamp_str:
        try:
            session_date = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).date()
        except Exception:
            session_date = date.today()

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Idempotency check via processed_events table
            if event_id:
                try:
                    await conn.execute(
                        "INSERT INTO processed_events (event_id) VALUES ($1)",
                        event_id,
                    )
                except Exception:
                    # Unique violation -> already processed
                    return None

            if not blipp_id:
                return {"user_id": user_id, "event_type": event_type}

            # 2. Lookup blipp details from local metadata projection
            meta_row = await conn.fetchrow(
                """
                SELECT creator_id, duration_seconds
                FROM analytics_blipp_metadata
                WHERE blipp_id = $1
                """,
                blipp_id,
            )

            if meta_row:
                creator_id = meta_row["creator_id"]
                effective_duration = float(meta_row["duration_seconds"] or duration_seconds or 1.0)
            elif creator_id_fallback:
                creator_id = creator_id_fallback
                effective_duration = max(float(duration_seconds), 1.0)
                await conn.execute(
                    """
                    INSERT INTO analytics_blipp_metadata (blipp_id, creator_id, duration_seconds)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (blipp_id) DO NOTHING
                    """,
                    blipp_id,
                    creator_id,
                    effective_duration,
                )
            else:
                logger.warning(
                    f"Blipp {blipp_id} not found in analytics projection or event fallback. Skipping aggregation."
                )
                return None

            effective_duration = max(effective_duration, 1.0)

            # Non-playback engagement
            if event_type in ("like", "unlike", "save", "unsave", "share"):
                return {
                    "user_id": user_id,
                    "blipp_id": blipp_id,
                    "event_type": event_type,
                    "creator_id": creator_id,
                }

            # 3. Lookup existing session
            existing_session = None
            if session_id:
                existing_session = await conn.fetchrow(
                    """
                    SELECT total_seconds_listened, completed, drop_off_position_seconds
                    FROM listening_session_agg
                    WHERE session_id = $1
                    """,
                    session_id,
                )

            current_listened = float(existing_session["total_seconds_listened"]) if existing_session else 0.0
            was_completed = bool(existing_session["completed"]) if existing_session else False

            delta_seconds = 0.0
            if event_type == "play_progress":
                if existing_session and position_seconds > float(existing_session.get("drop_off_position_seconds") or 0.0):
                    delta_seconds = position_seconds - float(existing_session["drop_off_position_seconds"] or 0.0)
                elif not existing_session:
                    delta_seconds = min(position_seconds, 15.0)

            new_total_listened = current_listened + max(delta_seconds, 0.0)
            new_completed = was_completed or (new_total_listened >= 0.9 * effective_duration)

            # 4. Upsert session aggregation
            if session_id:
                await conn.execute(
                    """
                    INSERT INTO listening_session_agg (
                        session_id, user_id, blipp_id, total_seconds_listened,
                        completed, drop_off_position_seconds, session_date
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (session_id) DO UPDATE SET
                        total_seconds_listened = EXCLUDED.total_seconds_listened,
                        completed = EXCLUDED.completed,
                        drop_off_position_seconds = EXCLUDED.drop_off_position_seconds
                    """,
                    session_id,
                    user_id,
                    blipp_id,
                    new_total_listened,
                    new_completed,
                    position_seconds,
                    session_date,
                )

            # 5. Creator minutes aggregation
            if delta_seconds > 0:
                delta_minutes = delta_seconds / 60.0
                await conn.execute(
                    """
                    INSERT INTO creator_minutes_agg (creator_id, blipp_id, total_minutes_listened, date)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (creator_id, blipp_id, date) DO UPDATE SET
                        total_minutes_listened = creator_minutes_agg.total_minutes_listened + EXCLUDED.total_minutes_listened
                    """,
                    creator_id,
                    blipp_id,
                    delta_minutes,
                    session_date,
                )

            return {
                "user_id": user_id,
                "blipp_id": blipp_id,
                "session_id": session_id,
                "event_type": event_type,
                "creator_id": creator_id,
                "total_seconds_listened": new_total_listened,
                "completed": new_completed,
                "delta_seconds": delta_seconds,
            }


async def push_gorse_feedback(user_id: str, blipp_id: str, timestamp_str: Optional[str], feedback_type: str) -> None:
    gorse_base = getattr(settings, "GORSE_API_URL", "http://gorse.blipp.svc.cluster.local:8088").rstrip("/")
    url = f"{gorse_base}/api/feedback"
    client = await get_http_client()
    payload = [{
        "FeedbackType": feedback_type,
        "UserId": user_id,
        "ItemId": blipp_id,
        "Timestamp": timestamp_str or datetime.now(timezone.utc).isoformat(),
    }]
    headers = {"Content-Type": "application/json"}
    if getattr(settings, "GORSE_API_KEY", ""):
        headers["X-API-Key"] = settings.GORSE_API_KEY
    try:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            logger.debug(f"Pushed Gorse feedback: user={user_id} blipp={blipp_id} type={feedback_type}")
        else:
            logger.warning(f"Gorse feedback rejected ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to push Gorse feedback for user={user_id} blipp={blipp_id}: {e}")


async def ensure_streams(js: JetStreamContext) -> None:
    stream_name = settings.NATS_STREAM_ENGAGEMENT
    subjects = [settings.NATS_SUBJECT_ENGAGEMENT]
    try:
        await js.stream_info(stream_name)
        try:
            await js.update_stream(name=stream_name, subjects=subjects)
        except Exception:
            pass
    except Exception:
        try:
            await js.add_stream(
                name=stream_name,
                subjects=subjects,
                storage=StorageType.FILE,
                retention=RetentionPolicy.LIMITS,
            )
        except Exception as e:
            logger.warning(f"Could not create stream '{stream_name}': {e}")


async def process_message(js: JetStreamContext, msg) -> None:
    raw_data = msg.data.decode("utf-8")
    try:
        data = json.loads(raw_data)
    except Exception as e:
        logger.error(f"Malformed JSON in engagement event: {e}")
        await msg.ack()
        return

    # Handle blipp published event to update local metadata projection
    if msg.subject == "engagement.blipp.published":
        blipp_id_str = data.get("blipp_id")
        creator_id_str = data.get("creator_id")
        duration = float(data.get("duration_seconds", 0.0))
        title = data.get("title", "")
        if blipp_id_str and creator_id_str:
            try:
                bid = uuid.UUID(str(blipp_id_str))
                cid = uuid.UUID(str(creator_id_str))
                pool = await get_db_pool(settings)
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO analytics_blipp_metadata (blipp_id, creator_id, duration_seconds, title)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (blipp_id) DO UPDATE SET
                            duration_seconds = EXCLUDED.duration_seconds,
                            title = EXCLUDED.title
                        """,
                        bid, cid, duration, title,
                    )
                logger.info(f"Analytics projection recorded blipp {bid} (creator={cid})")
            except Exception as e:
                logger.warning(f"Failed to record blipp metadata projection in analytics: {e}")
        await msg.ack()
        return

    try:
        event_id_str = data.get("event_id")
        user_id_str = data.get("user_id")
        blipp_id_str = data.get("blipp_id")
        creator_id_str = data.get("creator_id")
        session_id_str = data.get("session_id")
        event_type = data.get("event_type", "play_progress")
        device_signal = data.get("device_signal", "screen_on")
        position_seconds = float(data.get("position_seconds", 0.0))
        duration_seconds = float(data.get("duration_seconds", 0.0))
        timestamp = data.get("occurred_at") or data.get("timestamp")

        if not user_id_str:
            logger.warning(f"Missing user_id in engagement event: {data}")
            await msg.ack()
            return

        event_id = uuid.UUID(event_id_str) if event_id_str else None
        user_id = uuid.UUID(user_id_str)
        blipp_id = uuid.UUID(blipp_id_str) if blipp_id_str else None
        creator_id = uuid.UUID(creator_id_str) if creator_id_str else None
        session_id = uuid.UUID(session_id_str) if session_id_str else None

        res = await record_playback_engagement(
            event_id=event_id,
            session_id=session_id,
            user_id=user_id,
            blipp_id=blipp_id,
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
            event_type=event_type,
            device_signal=device_signal,
            timestamp_str=timestamp,
            creator_id_fallback=creator_id,
        )

        if res:
            is_positive = False
            feedback_type = "listen"

            if event_type in ("like", "save", "share"):
                is_positive = True
                feedback_type = event_type
            elif event_type in ("unlike", "unsave"):
                pass
            else:
                is_positive = (
                    bool(res.get("completed", False)) or
                    float(res.get("total_seconds_listened", 0.0)) >= 30.0 or
                    (duration_seconds > 0 and float(res.get("total_seconds_listened", 0.0)) >= 0.9 * duration_seconds)
                )

            if is_positive and blipp_id_str:
                asyncio.create_task(
                    push_gorse_feedback(
                        user_id=str(user_id),
                        blipp_id=str(blipp_id),
                        timestamp_str=timestamp,
                        feedback_type=feedback_type,
                    )
                )

        await msg.ack()

    except Exception as e:
        logger.exception(f"Error processing engagement event: {e}")
        try:
            await msg.nak(delay=2.0)
        except Exception as nak_err:
            logger.error(f"Failed to nak message: {nak_err}")


async def run_worker() -> None:
    global _running

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("Initializing analytics worker database pool...")
    await init_db(settings)
    await init_analytics_db()

    logger.info(f"Connecting to NATS at {settings.NATS_URL}...")
    nc: NATSClient = await nats.connect(
        servers=[settings.NATS_URL],
        name="analytics-worker",
        reconnect_time_wait=2,
        max_reconnect_attempts=60,
    )
    js = nc.jetstream()

    await ensure_streams(js)

    logger.info(f"Binding durable pull consumer '{NATS_CONSUMER_GROUP}' on stream '{settings.NATS_STREAM_ENGAGEMENT}'...")
    psub = await js.pull_subscribe(
        subject=settings.NATS_SUBJECT_ENGAGEMENT,
        durable=NATS_CONSUMER_GROUP,
        stream=settings.NATS_STREAM_ENGAGEMENT,
    )

    logger.info("Analytics Worker ready and waiting for playback events...")

    while _running:
        try:
            msgs = await psub.fetch(batch=10, timeout=2.0)
            for msg in msgs:
                await process_message(js, msg)
        except (nats.errors.TimeoutError, asyncio.TimeoutError):
            continue
        except Exception as e:
            if _running:
                logger.warning(f"Error in analytics pull fetch loop: {e}")
                await asyncio.sleep(1.0)

    logger.info("Analytics Worker shutting down, closing connections...")
    try:
        await psub.unsubscribe()
        await nc.drain()
        await nc.close()
    except Exception as e:
        logger.warning(f"Error during NATS close: {e}")
    await close_db()

    global _http_client
    if _http_client and not _http_client.is_closed:
        try:
            await _http_client.aclose()
        except Exception as e:
            logger.warning(f"Error closing HTTP client: {e}")

    logger.info("Analytics Worker shutdown complete.")


def main():
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
