import json
import uuid
import signal
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone, date

import httpx
import nats
from nats.aio.client import Client as NATSClient
from nats.js.client import JetStreamContext
from nats.js.api import StreamConfig, StorageType, RetentionPolicy

from blipp_common.config import settings
from blipp_common.database import get_db_pool, init_db, close_db

# Worker-specific NATS consumer group (overrides blipp_common default "blipp-workers")
NATS_CONSUMER_GROUP = "analytics-workers"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("analytics-worker")

_running = True
_http_client: Optional[httpx.AsyncClient] = None


def handle_shutdown(sig, frame):
    global _running
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    _running = False


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=3.0)
    return _http_client


# ─── Business SQL helper ──────────────────────────────────────────────────────


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
) -> Optional[Dict[str, Any]]:
    """
    Applies Section 6.5 aggregation business logic atomically:
    1. Treats background listening ('screen_off', 'bluetooth_connected', 'app_backgrounded')
       as active playback engagement.
    2. Aggregates total_seconds_listened and drop_off_position_seconds.
    3. Checks completion threshold (>= 0.9 * duration).
    4. Increments CreatorMinutesAgg.total_minutes_listened for the blipp's creator.
    """
    pool = await get_db_pool(settings)

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
            )

            # Idempotency check via processed_events table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id UUID PRIMARY KEY,
                    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )

            if event_id:
                try:
                    await conn.execute(
                        "INSERT INTO processed_events (event_id) VALUES ($1)",
                        event_id,
                    )
                except Exception:
                    # Unique violation -> already processed
                    return None

            # 2. Lookup blipp details (creator_id, official duration)
            if not blipp_id:
                # E.g. follow events do not have a blipp_id
                return {"user_id": user_id, "event_type": event_type}

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

            # If it's a non-playback event, we don't aggregate seconds.
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
            if session_id:
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


# ─── Gorse feedback / stream helpers ─────────────────────────────────────────


async def push_gorse_feedback(
    user_id: str, blipp_id: str, timestamp_str: Optional[str] = None, feedback_type: str = "listen"
) -> None:
    """
    Sends positive engagement feedback to the Gorse REST API (POST /api/feedback).
    Schema: [{"FeedbackType": "listen", "UserId": user_id, "ItemId": blipp_id, "Timestamp": ISO8601}]
    Executed in an async task to prevent HTTP network latency from blocking NATS acks.
    """
    try:
        client = await get_http_client()
        url = f"{settings.GORSE_API_URL.rstrip('/')}/api/feedback"
        ts = timestamp_str or datetime.now(timezone.utc).isoformat()
        payload = [
            {
                "FeedbackType": feedback_type,
                "UserId": user_id,
                "ItemId": blipp_id,
                "Timestamp": ts,
            }
        ]
        headers = {"Content-Type": "application/json"}
        if settings.GORSE_API_KEY:
            headers["X-API-Key"] = settings.GORSE_API_KEY

        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code < 300:
            logger.debug(f"Pushed Gorse feedback: user={user_id} blipp={blipp_id}")
        else:
            logger.warning(f"Gorse feedback rejected ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to push Gorse feedback for user={user_id} blipp={blipp_id}: {e}")


async def ensure_streams(js: JetStreamContext) -> None:
    """
    Ensures that stream ENGAGEMENT exists with subject engagement.>
    """
    stream_name = settings.NATS_STREAM_ENGAGEMENT
    subjects = [settings.NATS_SUBJECT_ENGAGEMENT]
    try:
        await js.stream_info(stream_name)
        try:
            await js.update_stream(name=stream_name, subjects=subjects)
            logger.info(f"Updated stream '{stream_name}' subjects to {subjects}")
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
            logger.info(f"Created stream '{stream_name}' with subjects {subjects}")
        except Exception as e:
            logger.warning(f"Could not create stream '{stream_name}': {e}")


async def process_message(js: JetStreamContext, msg) -> None:
    raw_data = msg.data.decode("utf-8")
    logger.debug(f"Processing engagement event on subject '{msg.subject}': {raw_data}")
    try:
        data = json.loads(raw_data)
    except Exception as e:
        logger.error(f"Malformed JSON in engagement message: {e}")
        await msg.ack()
        return

    try:
        event_id_str = data.get("event_id")
        user_id_str = data.get("user_id")
        blipp_id_str = data.get("blipp_id")
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
        session_id = uuid.UUID(session_id_str) if session_id_str else None

        # Section 6.5: Aggregate session & creator analytics
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
        )

        if res:
            logger.info(
                f"Processed event {event_type} for user {user_id_str}. "
                f"Stats: completed={res.get('completed', False)}"
            )

            is_positive = False
            feedback_type = "listen"

            if event_type in ("like", "save", "share"):
                is_positive = True
                feedback_type = event_type
            elif event_type in ("unlike", "unsave"):
                # We could delete feedback in Gorse, but for now we'll just skip sending positive
                pass
            else:
                # Playback threshold
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
