import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import nats
from nats.js.api import RetentionPolicy, StorageType

from blipp_common.config import settings
from blipp_common.database import get_db_pool
from blipp_common.events import event_bus

logger = logging.getLogger("content-ingest.event_handlers")

_running = True

CONSUMER_NAME = "content-ingest-transcode"


def stop_event_handlers() -> None:
    """Signals background worker loops to terminate gracefully."""
    global _running
    _running = False
    logger.info("Stopping content-ingest event handlers...")


# ─── 1. Transcode Completion & Copyright Consumer ──────────────────────────────


async def handle_transcode_completed(data: Dict[str, Any]) -> None:
    """
    Handles media.transcode.completed event:
    1. Updates uploads.processing_status = 'done'
    2. Evaluates copyright scanning feature flag & scheduling
    3. Persists/upserts blipp record into blipp_ingest database
    4. Publishes copyright.scan.requested or engagement.blipp.published event
    """
    upload_id_str = data.get("upload_id")
    if not upload_id_str:
        logger.warning(f"Missing upload_id in transcode completed event: {data}")
        return

    import uuid
    try:
        upload_id = uuid.UUID(str(upload_id_str))
        creator_id_str = data.get("creator_id")
        creator_id = uuid.UUID(str(creator_id_str)) if creator_id_str else None

        blipp_id_str = data.get("blipp_id")
        if not blipp_id_str:
            logger.error(f"Missing blipp_id in transcode completed event: {data}")
            return
        blipp_id = uuid.UUID(str(blipp_id_str))
    except (ValueError, TypeError):
        logger.error(f"Invalid UUID in transcode completed event: {data}")
        return

    title = data.get("title") or "Untitled Blipp"
    description = data.get("description")
    audio_url = data.get("audio_url", "")
    audio_variants = data.get("audio_variants", {})
    duration_seconds = float(data.get("duration_seconds", 0.0))
    source_type = data.get("source_type", "direct_upload")
    scheduled_at_raw = data.get("scheduled_at")

    now_utc = datetime.now(timezone.utc)
    scheduled_at_dt: Optional[datetime] = None
    if scheduled_at_raw:
        if isinstance(scheduled_at_raw, str):
            try:
                scheduled_at_dt = datetime.fromisoformat(scheduled_at_raw)
            except Exception:
                scheduled_at_dt = None
        elif isinstance(scheduled_at_raw, datetime):
            scheduled_at_dt = scheduled_at_raw

    pool = await get_db_pool()
    if not pool:
        logger.error("Database pool unavailable to process transcode completed event")
        return

    # If creator_id is missing, hydrate from uploads record
    if not creator_id:
        async with pool.acquire() as conn:
            creator_id = await conn.fetchval(
                "SELECT creator_id FROM uploads WHERE upload_id = $1", upload_id
            )

    if not creator_id:
        logger.error(f"Cannot resolve creator_id for upload {upload_id}")
        return

    # Determine status: copyright review -> scheduled -> published
    if settings.FEATURE_COPYRIGHT_SCAN_ENABLED:
        blipp_status = "processing"
    elif scheduled_at_dt and scheduled_at_dt > now_utc:
        blipp_status = "scheduled"
    else:
        blipp_status = "published"

    author_username = data.get("author_username") or ""
    author_display_name = data.get("author_display_name") or author_username or "Creator"
    author_avatar_url = data.get("author_avatar_url")

    published_payload = {
        "blipp_id": str(blipp_id),
        "creator_id": str(creator_id),
        "title": title,
        "description": description,
        "audio_url": audio_url,
        "audio_variants": audio_variants,
        "duration_seconds": duration_seconds,
        "published_at": now_utc.isoformat(),
        "author_username": author_username,
        "author_display_name": author_display_name,
        "author_avatar_url": author_avatar_url,
    }

    copyright_payload = {
        "blipp_id": str(blipp_id),
        "upload_id": str(upload_id),
        "audio_url": audio_url,
        "duration_seconds": duration_seconds,
        "requested_at": now_utc.isoformat(),
    }

    from blipp_common.outbox import record_outbox_event

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Update source upload record
            await conn.execute(
                """
                UPDATE uploads
                SET processing_status = $1
                WHERE upload_id = $2
                """,
                blipp_status,
                upload_id,
            )

            # 2. Upsert blipps record
            await conn.execute(
                """
                INSERT INTO blipps (
                    blipp_id, creator_id, title, description, audio_url, audio_variants,
                    duration_seconds, language, status, scheduled_at, source_type, parent_upload_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'en', $8, $9, $10, $11, $12)
                ON CONFLICT (blipp_id) DO UPDATE
                    SET audio_url = EXCLUDED.audio_url,
                        audio_variants = EXCLUDED.audio_variants,
                        duration_seconds = EXCLUDED.duration_seconds,
                        status = EXCLUDED.status,
                        scheduled_at = EXCLUDED.scheduled_at
                """,
                blipp_id,
                creator_id,
                title,
                description,
                audio_url,
                json.dumps(audio_variants),
                duration_seconds,
                blipp_status,
                scheduled_at_dt,
                source_type,
                upload_id,
                now_utc,
            )

            # 3. Record outbox event within the same atomic transaction
            if blipp_status == "published":
                await record_outbox_event(conn, "engagement.blipp.published", published_payload)
            elif blipp_status == "processing":
                await record_outbox_event(conn, "copyright.scan.requested", copyright_payload)

            logger.info(f"Persisted blipp {blipp_id} and recorded outbox (status={blipp_status})")

    # T21: Outbox is the ONLY publisher.
    # Removed eager event_bus.publish() for both engagement.blipp.published and
    # copyright.scan.requested. The outbox background task handles delivery.
    if blipp_status == "published":
        logger.info(f"Recorded engagement.blipp.published in outbox for blipp {blipp_id}")
    elif blipp_status == "processing":
        logger.info(f"Recorded copyright.scan.requested in outbox for blipp {blipp_id}")


async def handle_transcode_failed(data: Dict[str, Any]) -> None:
    """Updates uploads.processing_status = 'failed' when worker reports fatal error."""
    upload_id_str = data.get("upload_id")
    if not upload_id_str:
        return
    import uuid
    try:
        upload_id = uuid.UUID(str(upload_id_str))
    except (ValueError, TypeError):
        logger.error(f"Invalid UUID in transcode failed event: {data}")
        return
    pool = await get_db_pool()
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploads SET processing_status = 'failed' WHERE upload_id = $1",
                upload_id,
            )
            logger.info(f"Marked upload {upload_id} as failed after fatal transcode error")


async def run_transcode_consumer() -> None:
    """
    Subscribes to media.transcode.> events from NATS JetStream (UPLOADS stream)
    using durable consumer 'content-ingest-transcode'.
    """
    global _running

    while _running:
        if not event_bus.is_connected or not event_bus.js:
            connected = await event_bus.connect("content-ingest-transcode-consumer")
            if not connected:
                await asyncio.sleep(2.0)
                continue

        js = event_bus.js
        try:
            # Bind or declare durable consumer
            psub = await js.pull_subscribe(
                subject="media.transcode.>",
                durable=CONSUMER_NAME,
                stream=settings.NATS_STREAM_UPLOADS,
            )
            logger.info(f"Durable pull consumer '{CONSUMER_NAME}' subscribed to 'media.transcode.>'")

            while _running:
                try:
                    msgs = await psub.fetch(batch=5, timeout=2.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            if msg.subject == "media.transcode.completed":
                                await handle_transcode_completed(payload)
                            elif msg.subject == "media.transcode.failed":
                                await handle_transcode_failed(payload)
                            await msg.ack()
                        except Exception as msg_err:
                            logger.exception(f"Error handling message on {msg.subject}: {msg_err}")
                            await msg.nak(delay=2.0)
                except (nats.errors.TimeoutError, asyncio.TimeoutError):
                    continue
                except asyncio.CancelledError:
                    _running = False
                    break
                except Exception as loop_err:
                    if _running:
                        logger.warning(f"Error in transcode fetch loop: {loop_err}")
                        await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            break
        except Exception as conn_err:
            if _running:
                logger.warning(f"NATS subscription connection error: {conn_err}. Reconnecting in 3s...")
                await asyncio.sleep(3.0)

    logger.info("Transcode consumer background task stopped.")


# ─── 2. Scheduled Post Publisher ───────────────────────────────────────────────


async def publish_due_scheduled_blipps() -> int:
    """
    Finds blipps with status = 'scheduled' and scheduled_at <= NOW(),
    locks rows with FOR UPDATE SKIP LOCKED, transitions to 'published',
    and emits engagement.blipp.published events.
    """
    pool = await get_db_pool()
    if not pool:
        return 0

    published_count = 0
    now_utc = datetime.now(timezone.utc)

    # T26: Route through the transactional outbox — NOT direct event_bus.publish().
    # This guarantees the engagement.blipp.published event is delivered even if NATS
    # is temporarily unavailable at the moment the scheduler runs.
    try:
        from blipp_common.outbox import record_outbox_event
        async with pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT blipp_id, creator_id, title, description, audio_url,
                           audio_variants, duration_seconds, scheduled_at
                    FROM blipps
                    WHERE status = 'scheduled' AND scheduled_at <= NOW()
                    FOR UPDATE SKIP LOCKED
                    """
                )

                if rows:
                    blipp_ids = [r["blipp_id"] for r in rows]
                    await conn.execute(
                        """
                        UPDATE blipps
                        SET status = 'published'
                        WHERE blipp_id = ANY($1::uuid[])
                        """,
                        blipp_ids,
                    )

                    for r in rows:
                        published_count += 1
                        published_payload = {
                            "blipp_id": str(r["blipp_id"]),
                            "creator_id": str(r["creator_id"]),
                            "title": r["title"] or "",
                            "description": r.get("description") or "",
                            "audio_url": r["audio_url"],
                            "audio_variants": r.get("audio_variants") or {},
                            "duration_seconds": float(r["duration_seconds"] or 0.0),
                            "published_at": now_utc.isoformat(),
                            "source": "scheduled_publisher",
                        }
                        # Record in outbox WITHIN the same transaction — atomically
                        # with the status UPDATE. The outbox publisher delivers to NATS.
                        await record_outbox_event(
                            conn,
                            "engagement.blipp.published",
                            published_payload,
                        )

                    logger.info(f"Scheduled publisher released {published_count} blipp(s) via outbox")

    except Exception as e:
        logger.exception(f"Error during scheduled publisher execution: {e}")

    return published_count


async def run_scheduled_publisher() -> None:
    """Periodic background loop that releases scheduled posts when due."""
    global _running
    interval = max(5, settings.SCHEDULED_PUBLISH_INTERVAL_SECONDS)
    logger.info(f"Starting scheduled post publisher loop (interval={interval}s)...")

    while _running:
        try:
            await publish_due_scheduled_blipps()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Error in scheduled publisher tick: {e}")

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break

    logger.info("Scheduled post publisher background task stopped.")


# ─── 3. Content Takedown Consumer (§6.7) ───────────────────────────────────────

TAKEDOWN_CONSUMER_NAME = "content-ingest-takedown"


async def handle_content_takedown(data: Dict[str, Any]) -> None:
    """
    Handles content.takedown event (§6.7):
    Updates blipps.status = 'taken_down' in blipp_ingest database,
    instantly revoking feed visibility.
    """
    blipp_id_str = data.get("blipp_id")
    if not blipp_id_str:
        logger.warning(f"Missing blipp_id in content.takedown event: {data}")
        return

    try:
        blipp_id = uuid.UUID(blipp_id_str)
    except (ValueError, TypeError):
        logger.error(f"Invalid blipp_id UUID in content.takedown: {blipp_id_str}")
        return

    pool = await get_db_pool()
    if not pool:
        logger.error("Database pool unavailable to process content takedown event")
        return

    reason = data.get("reason", "moderation_action")

    from blipp_common.outbox import record_outbox_event

    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute(
                """
                UPDATE blipps
                SET status = 'taken_down'
                WHERE blipp_id = $1
                """,
                blipp_id,
            )
            if res == "UPDATE 1":
                # T30: Emit a takedown event through the outbox so the Feed service
                # receives it and removes the blipp from feed_items projection.
                # The outbox guarantees at-least-once delivery even if NATS is down.
                await record_outbox_event(
                    conn,
                    "content.takedown",
                    {
                        "blipp_id": str(blipp_id),
                        "reason": reason,
                    },
                )
                logger.info(f"Processed content takedown for blipp {blipp_id} (reason='{reason}'): {res}. Outbox event recorded.")
            else:
                logger.warning(f"Content takedown for blipp {blipp_id}: no row updated (blipp not found?): {res}")


async def run_takedown_consumer() -> None:
    """
    Subscribes to content.takedown events from NATS JetStream (UPLOADS stream)
    using durable consumer 'content-ingest-takedown'.
    """
    global _running

    while _running:
        if not event_bus.is_connected or not event_bus.js:
            connected = await event_bus.connect("content-ingest-takedown-consumer")
            if not connected:
                await asyncio.sleep(2.0)
                continue

        js = event_bus.js
        try:
            psub = await js.pull_subscribe(
                subject="content.takedown",
                durable=TAKEDOWN_CONSUMER_NAME,
                stream=settings.NATS_STREAM_UPLOADS,
            )
            logger.info(f"Durable pull consumer '{TAKEDOWN_CONSUMER_NAME}' subscribed to 'content.takedown'")

            while _running:
                try:
                    msgs = await psub.fetch(batch=5, timeout=2.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            await handle_content_takedown(payload)
                            await msg.ack()
                        except Exception as msg_err:
                            logger.exception(f"Error handling message on {msg.subject}: {msg_err}")
                            await msg.nak(delay=2.0)
                except (nats.errors.TimeoutError, asyncio.TimeoutError):
                    continue
                except asyncio.CancelledError:
                    _running = False
                    break
                except Exception as loop_err:
                    if _running:
                        logger.warning(f"Error in takedown fetch loop: {loop_err}")
                        await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            break
        except Exception as conn_err:
            if _running:
                logger.warning(f"NATS subscription connection error in takedown consumer: {conn_err}. Reconnecting in 3s...")
                await asyncio.sleep(3.0)

    logger.info("Content takedown consumer background task stopped.")

