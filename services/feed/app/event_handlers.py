import asyncio
import json
import logging
import uuid
from typing import Any, Dict

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
    Project published blipps into feed_items table strictly from event payload
    without cross-service database access.
    """
    blipp_id_str = data.get("blipp_id")
    if not blipp_id_str:
        return

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

    title = data.get("title") or "Untitled Blipp"
    description = data.get("description")
    audio_url = data.get("audio_url", "")
    audio_variants = data.get("audio_variants") or {}
    duration_seconds = float(data.get("duration_seconds", 0.0))
    username = data.get("author_username") or "creator"
    display_name = data.get("author_display_name") or username
    avatar_url = data.get("author_avatar_url")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feed_items (
                blipp_id, creator_id, title, description, audio_url, audio_variants,
                duration_seconds, author_username, author_display_name, author_avatar_url
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10)
            ON CONFLICT (blipp_id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                audio_url = EXCLUDED.audio_url,
                audio_variants = EXCLUDED.audio_variants,
                duration_seconds = EXCLUDED.duration_seconds,
                author_username = EXCLUDED.author_username,
                author_display_name = EXCLUDED.author_display_name,
                author_avatar_url = EXCLUDED.author_avatar_url
            """,
            blipp_id,
            creator_id,
            title,
            description,
            audio_url,
            json.dumps(audio_variants),
            duration_seconds,
            username,
            display_name,
            avatar_url,
        )
        logger.info(f"Projected blipp {blipp_id} to feed_items (author snapshot included)")


async def handle_like_event(data: Dict[str, Any], is_like: bool) -> None:
    user_id_str = data.get("user_id")
    blipp_id_str = data.get("blipp_id")
    if not user_id_str or not blipp_id_str:
        return

    try:
        user_id = uuid.UUID(str(user_id_str))
        blipp_id = uuid.UUID(str(blipp_id_str))
    except (ValueError, TypeError):
        return

    pool = await get_db_pool()
    if not pool:
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            if is_like:
                await conn.execute(
                    """
                    INSERT INTO user_likes_projection (user_id, blipp_id)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id, blipp_id) DO NOTHING
                    """,
                    user_id,
                    blipp_id,
                )
                await conn.execute(
                    """
                    INSERT INTO feed_item_stats (blipp_id, likes_count)
                    VALUES ($1, 1)
                    ON CONFLICT (blipp_id) DO UPDATE
                    SET likes_count = feed_item_stats.likes_count + 1
                    """,
                    blipp_id,
                )
            else:
                res = await conn.execute(
                    "DELETE FROM user_likes_projection WHERE user_id = $1 AND blipp_id = $2",
                    user_id,
                    blipp_id,
                )
                if res == "DELETE 1":
                    await conn.execute(
                        """
                        UPDATE feed_item_stats
                        SET likes_count = GREATEST(0, likes_count - 1)
                        WHERE blipp_id = $1
                        """,
                        blipp_id,
                    )


async def handle_save_event(data: Dict[str, Any], is_save: bool) -> None:
    user_id_str = data.get("user_id")
    blipp_id_str = data.get("blipp_id")
    if not user_id_str or not blipp_id_str:
        return

    try:
        user_id = uuid.UUID(str(user_id_str))
        blipp_id = uuid.UUID(str(blipp_id_str))
    except (ValueError, TypeError):
        return

    pool = await get_db_pool()
    if not pool:
        return

    async with pool.acquire() as conn:
        if is_save:
            await conn.execute(
                """
                INSERT INTO user_saves_projection (user_id, blipp_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id, blipp_id) DO NOTHING
                """,
                user_id,
                blipp_id,
            )
        else:
            await conn.execute(
                "DELETE FROM user_saves_projection WHERE user_id = $1 AND blipp_id = $2",
                user_id,
                blipp_id,
            )


async def handle_follow_event(data: Dict[str, Any], is_follow: bool) -> None:
    follower_id_str = data.get("user_id")
    followee_id_str = data.get("target_user_id")
    if not follower_id_str or not followee_id_str:
        return

    try:
        follower_id = uuid.UUID(str(follower_id_str))
        followee_id = uuid.UUID(str(followee_id_str))
    except (ValueError, TypeError):
        return

    pool = await get_db_pool()
    if not pool:
        return

    async with pool.acquire() as conn:
        if is_follow:
            await conn.execute(
                """
                INSERT INTO user_follows_projection (follower_id, followee_id)
                VALUES ($1, $2)
                ON CONFLICT (follower_id, followee_id) DO NOTHING
                """,
                follower_id,
                followee_id,
            )
        else:
            await conn.execute(
                "DELETE FROM user_follows_projection WHERE follower_id = $1 AND followee_id = $2",
                follower_id,
                followee_id,
            )


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
                subject="engagement.>",
                durable=CONSUMER_NAME,
                stream=settings.NATS_STREAM_ENGAGEMENT,
            )
            logger.info(f"Durable pull consumer '{CONSUMER_NAME}' subscribed to 'engagement.>'")

            while _running:
                try:
                    msgs = await psub.fetch(batch=10, timeout=2.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            subject = msg.subject

                            if subject == "engagement.blipp.published":
                                await handle_blipp_published(payload)
                            elif subject == "engagement.like":
                                await handle_like_event(payload, is_like=True)
                            elif subject == "engagement.unlike":
                                await handle_like_event(payload, is_like=False)
                            elif subject == "engagement.save":
                                await handle_save_event(payload, is_save=True)
                            elif subject == "engagement.unsave":
                                await handle_save_event(payload, is_save=False)
                            elif subject == "engagement.follow":
                                await handle_follow_event(payload, is_follow=True)
                            elif subject == "engagement.unfollow":
                                await handle_follow_event(payload, is_follow=False)

                            await msg.ack()
                        except Exception as msg_err:
                            logger.exception(f"Error handling msg on '{msg.subject}': {msg_err}")
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
