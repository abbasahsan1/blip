import asyncio
import json
import logging
from typing import Dict, Any

import nats
from nats.js.api import RetentionPolicy, StorageType

from blipp_common.config import settings
from blipp_common.database import get_db_pool
from blipp_common.events import event_bus

logger = logging.getLogger("feed-service.event_handlers")

_running = True
CONSUMER_NAME = "feed-service-projection"


def stop_event_handlers() -> None:
    global _running
    _running = False
    logger.info("Stopping feed-service event handlers...")


async def handle_blipp_published(data: Dict[str, Any]) -> None:
    """
    Project published blipps into feed_items table for Feed isolation.
    """
    blipp_id_str = data.get("blipp_id")
    if not blipp_id_str:
        return

    import uuid
    try:
        blipp_id = uuid.UUID(str(blipp_id_str))
        creator_id_str = data.get("creator_id")
        creator_id = uuid.UUID(str(creator_id_str)) if creator_id_str else uuid.uuid4()
    except (ValueError, TypeError):
        logger.error(f"Invalid UUID in published event: {data}")
        return

    pool = await get_db_pool()
    if not pool:
        logger.error("Database pool unavailable to process event")
        return

    title = data.get("title")
    audio_url = data.get("audio_url", "")
    duration_seconds = float(data.get("duration_seconds", 0.0))
    published_at = data.get("published_at")
    
    # We may need to get user profile details for author_username etc.
    # In a fully decoupled system, we'd hydrate this. Since we share the db for now, 
    # we can fetch them from users_profile.
    
    async with pool.acquire() as conn:
        profile = await conn.fetchrow("SELECT username, display_name, avatar_url FROM users_profile WHERE user_id = $1", creator_id)
        
        username = profile["username"] if profile else "unknown"
        display_name = profile["display_name"] if profile and profile["display_name"] else username
        avatar_url = profile["avatar_url"] if profile else None

        await conn.execute(
            """
            INSERT INTO feed_items (
                blipp_id, creator_id, title, audio_url, duration_seconds, 
                author_username, author_display_name, author_avatar_url
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (blipp_id) DO UPDATE SET
                audio_url = EXCLUDED.audio_url,
                duration_seconds = EXCLUDED.duration_seconds
            """,
            blipp_id, creator_id, title, audio_url, duration_seconds,
            username, display_name, avatar_url
        )
        logger.info(f"Projected blipp {blipp_id} to feed_items")


async def run_event_consumer() -> None:
    global _running

    while _running:
        if not event_bus.is_connected or not event_bus.js:
            connected = await event_bus.connect("feed-service-consumer")
            if not connected:
                await asyncio.sleep(2.0)
                continue

        js = event_bus.js
        try:
            # We must ensure the stream exists
            try:
                await js.add_stream(
                    name=settings.NATS_STREAM_ENGAGEMENT,
                    subjects=["engagement.>"],
                    storage=StorageType.FILE,
                    retention=RetentionPolicy.LIMITS,
                )
            except Exception:
                pass
                
            psub = await js.pull_subscribe(
                subject="engagement.blipp.published",
                durable=CONSUMER_NAME,
                stream=settings.NATS_STREAM_ENGAGEMENT,
            )
            logger.info(f"Durable pull consumer '{CONSUMER_NAME}' subscribed to 'engagement.blipp.published'")

            while _running:
                try:
                    msgs = await psub.fetch(batch=5, timeout=2.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            await handle_blipp_published(payload)
                            await msg.ack()
                        except Exception as msg_err:
                            logger.exception(f"Error handling msg: {msg_err}")
                            await msg.nak(delay=2.0)
                except (nats.errors.TimeoutError, asyncio.TimeoutError):
                    continue
                except asyncio.CancelledError:
                    _running = False
                    break
                except Exception as loop_err:
                    if _running:
                        logger.warning(f"Error in fetch loop: {loop_err}")
                        await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as conn_err:
            if _running:
                logger.warning(f"NATS sub error: {conn_err}. Reconnecting...")
                await asyncio.sleep(3.0)

    logger.info("Feed consumer stopped.")
