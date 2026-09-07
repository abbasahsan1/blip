import json
import uuid
import signal
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

import httpx
import nats
from nats.aio.client import Client as NATSClient
from nats.js.client import JetStreamContext
from nats.js.api import StreamConfig, StorageType, RetentionPolicy

from app.config import settings
from app.database import (
    init_db,
    close_db,
    record_playback_engagement,
)

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


async def push_gorse_feedback(
    user_id: str, blipp_id: str, timestamp_str: Optional[str] = None
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
                "FeedbackType": "listen",
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
        user_id_str = data.get("user_id")
        blipp_id_str = data.get("blipp_id")
        session_id_str = data.get("session_id")
        event_type = data.get("event_type", "play_progress")
        device_signal = data.get("device_signal", "screen_on")
        position_seconds = float(data.get("position_seconds", 0.0))
        duration_seconds = float(data.get("duration_seconds", 0.0))
        timestamp = data.get("timestamp")

        if not user_id_str or not blipp_id_str or not session_id_str:
            logger.warning(f"Missing required UUID fields in engagement event: {data}")
            await msg.ack()
            return

        user_id = uuid.UUID(user_id_str)
        blipp_id = uuid.UUID(blipp_id_str)
        session_id = uuid.UUID(session_id_str)

        # Section 6.5: Aggregate session & creator analytics
        res = await record_playback_engagement(
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
                f"Aggregated session {session_id} (blipp={blipp_id}): "
                f"seconds={res['total_seconds_listened']:.1f}, "
                f"delta_mins={res['delta_minutes']:.3f}, "
                f"completed={res['completed']}"
            )

            # Section 6.5: Positive engagement threshold for Gorse recommender
            # (Completed listening session, listened >= 30s continuous, or >= 90% of duration)
            is_positive = (
                bool(res.get("completed", False)) or
                float(res.get("total_seconds_listened", 0.0)) >= 30.0 or
                (duration_seconds > 0 and float(res.get("total_seconds_listened", 0.0)) >= 0.9 * duration_seconds)
            )

            if is_positive:
                # Dispatch feedback asynchronously to not block the JetStream ack loop
                asyncio.create_task(
                    push_gorse_feedback(
                        user_id=str(user_id),
                        blipp_id=str(blipp_id),
                        timestamp_str=timestamp,
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
    await init_db()

    logger.info(f"Connecting to NATS at {settings.NATS_URL}...")
    nc: NATSClient = await nats.connect(
        servers=[settings.NATS_URL],
        name="analytics-worker",
        reconnect_time_wait=2,
        max_reconnect_attempts=60,
    )
    js = nc.jetstream()

    await ensure_streams(js)

    logger.info(f"Binding durable pull consumer '{settings.NATS_CONSUMER_GROUP}' on stream '{settings.NATS_STREAM_ENGAGEMENT}'...")
    psub = await js.pull_subscribe(
        subject=settings.NATS_SUBJECT_ENGAGEMENT,
        durable=settings.NATS_CONSUMER_GROUP,
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
