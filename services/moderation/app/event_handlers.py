import asyncio
import json
import logging
from typing import Dict, Any

import httpx
import nats

from blipp_common.config import settings
from blipp_common.events import event_bus

logger = logging.getLogger("moderation.event_handlers")

_running = True
CONSUMER_NAME = "moderation-copyright-consumer"


async def handle_copyright_cleared(data: Dict[str, Any]) -> None:
    """
    Handles copyright.cleared event by calling the Content Ingest service
    to update the blipp status to 'published'.
    """
    upload_id = data.get("upload_id")
    blipp_id = data.get("blipp_id")

    if not upload_id or not blipp_id:
        logger.warning(f"Missing upload_id or blipp_id in copyright.cleared event: {data}")
        return

    logger.info(f"Processing copyright.cleared for upload {upload_id}, blipp {blipp_id}")

    try:
        # Internal K8s DNS for content-ingest service
        ingest_url = f"http://content-ingest-service:8001/v1/uploads/{upload_id}/status"
        
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                ingest_url,
                json={"status": "published"}
            )
            response.raise_for_status()
            logger.info(f"Successfully updated status to published for upload {upload_id}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling content-ingest for upload {upload_id}: {e}. Response: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Network error calling content-ingest for upload {upload_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error calling content-ingest for upload {upload_id}: {e}")


async def run_copyright_consumer() -> None:
    global _running

    while _running:
        if not event_bus.is_connected or not event_bus.js:
            connected = await event_bus.connect("moderation-service-consumer")
            if not connected:
                await asyncio.sleep(2.0)
                continue

        js = event_bus.js
        try:
            psub = await js.pull_subscribe(
                subject="copyright.cleared",
                durable=CONSUMER_NAME,
                stream=settings.NATS_STREAM_UPLOADS,
            )
            logger.info(f"Durable pull consumer '{CONSUMER_NAME}' subscribed to 'copyright.cleared'")

            while _running:
                try:
                    msgs = await psub.fetch(batch=5, timeout=2.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            await handle_copyright_cleared(payload)
                            await msg.ack()
                        except Exception as msg_err:
                            logger.exception(f"Error handling message on {msg.subject}: {msg_err}")
                            await msg.ack()
                except (nats.errors.TimeoutError, asyncio.TimeoutError):
                    continue
                except asyncio.CancelledError:
                    _running = False
                    break
                except Exception as loop_err:
                    if _running:
                        logger.warning(f"Error in copyright fetch loop: {loop_err}")
                        await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            break
        except Exception as conn_err:
            if _running:
                logger.warning(f"NATS subscription error: {conn_err}. Reconnecting in 3s...")
                await asyncio.sleep(3.0)

    logger.info("Copyright consumer background task stopped.")


def stop_event_handlers() -> None:
    global _running
    _running = False
    logger.info("Stopping moderation event handlers...")
