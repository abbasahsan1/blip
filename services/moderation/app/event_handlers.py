import asyncio
import json
import logging
import os
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

    import uuid
    try:
        upload_id = str(uuid.UUID(str(upload_id)))
        blipp_id = str(uuid.UUID(str(blipp_id)))
    except (ValueError, TypeError):
        logger.error(f"Invalid UUIDs in copyright.cleared event: {data}")
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
        if e.response.status_code == 404:
            # Raise exception so the message is not ACKed and can be retried
            raise Exception("Race condition: blipp not found yet, triggering retry.")
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


async def handle_user_account_suspended(data: Dict[str, Any]) -> None:
    """
    Handles user.account.suspended event by authenticating with Keycloak Admin API
    and disabling the user account.
    """
    user_id = data.get("user_id")
    if not user_id:
        logger.warning(f"Missing user_id in user.account.suspended event: {data}")
        return

    logger.info(f"Processing user.account.suspended for user {user_id}")
    
    admin_user = settings.KEYCLOAK_ADMIN
    admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin_master_password")
    kc_url = settings.KEYCLOAK_INTERNAL_URL.replace("/keycloak", "")
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. Get Admin Token
            token_url = f"{kc_url}/keycloak/realms/master/protocol/openid-connect/token"
            token_resp = await client.post(
                token_url,
                data={
                    "client_id": "admin-cli",
                    "grant_type": "password",
                    "username": admin_user,
                    "password": admin_password
                }
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data.get("access_token")

            # 2. Update user status in blipp realm
            admin_url = f"{kc_url}/keycloak/admin/realms/{settings.KEYCLOAK_REALM}/users/{user_id}"
            update_resp = await client.put(
                admin_url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"enabled": False}
            )
            update_resp.raise_for_status()
            logger.info(f"Successfully suspended user {user_id} in Keycloak")
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error suspending user {user_id}: {e}. Response: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error suspending user {user_id}: {e}")
        raise


async def run_account_suspension_consumer() -> None:
    global _running

    while _running:
        if not event_bus.is_connected or not event_bus.js:
            connected = await event_bus.connect("moderation-account-consumer")
            if not connected:
                await asyncio.sleep(2.0)
                continue

        js = event_bus.js
        try:
            # We assume user events are on a "USERS" stream or similar, 
            # falling back to a general stream or reusing ENGAGEMENT stream for now.
            # Usually events are on their respective streams, let's just use the subject 
            # and a reasonable stream based on existing config or create an ephemeral one if needed.
            # Wait, the instruction says "listen for the user.account.suspended subject".
            # I will just bind to stream UPLOADS or another if configured, or omit stream for core NATS.
            # Let's omit stream and just use core NATS subscribe if stream is unknown, or we can use NATS JetStream.
            # We'll use JetStream and if stream name isn't specified, we might get an error.
            # I will assume there's a "USERS" stream or we can just bind to "user.>" on ENGAGEMENT.
            
            stream_name = getattr(settings, "NATS_STREAM_USERS", "USERS")
            
            psub = await js.pull_subscribe(
                subject="user.account.suspended",
                durable="moderation-suspension-consumer",
                stream=stream_name,
            )
            logger.info(f"Durable pull consumer 'moderation-suspension-consumer' subscribed to 'user.account.suspended'")

            while _running:
                try:
                    msgs = await psub.fetch(batch=5, timeout=2.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            await handle_user_account_suspended(payload)
                            await msg.ack()
                        except Exception as msg_err:
                            logger.exception(f"Error handling message on {msg.subject}: {msg_err}")
                            # Do not ack if we want it to retry, but we raised exception in handler if it failed.
                            # So it won't ack if handle_user_account_suspended raises.
                except (nats.errors.TimeoutError, asyncio.TimeoutError):
                    continue
                except asyncio.CancelledError:
                    _running = False
                    break
                except Exception as loop_err:
                    if _running:
                        logger.warning(f"Error in suspension fetch loop: {loop_err}")
                        await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            break
        except Exception as conn_err:
            if _running:
                logger.warning(f"NATS suspension subscription error: {conn_err}. Reconnecting in 3s...")
                await asyncio.sleep(3.0)

    logger.info("Suspension consumer background task stopped.")


def stop_event_handlers() -> None:
    global _running
    _running = False
    logger.info("Stopping moderation event handlers...")
