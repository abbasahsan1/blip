import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union
import nats
from nats.aio.client import Client as NATSClient
from nats.js.client import JetStreamContext
from nats.js.api import StreamConfig, RetentionPolicy, StorageType
from nats.js.errors import BadRequestError

from app.core.config import settings

logger = logging.getLogger("auth-service.events")


class EventBus:
    """
    Manages NATS JetStream connection lifecycle, stream declaration,
    and event publishing helpers.
    """

    def __init__(self):
        self.nc: Optional[NATSClient] = None
        self.js: Optional[JetStreamContext] = None
        self.is_connected: bool = False

    async def connect(self) -> bool:
        """
        Establishes connection to NATS, initializes JetStream,
        and ensures required streams are declared.
        """
        try:
            active_loop = asyncio.get_running_loop()
        except RuntimeError:
            active_loop = None

        current_loop = getattr(self.nc, "_loop", None)
        if (
            self.is_connected
            and self.nc
            and not self.nc.is_closed
            and current_loop
            and not current_loop.is_closed()
            and (active_loop is None or current_loop == active_loop)
        ):
            return True

        if self.nc:
            self.nc = None
            self.js = None
            self.is_connected = False

        logger.info(f"Connecting to NATS at {settings.NATS_URL}...")
        try:
            self.nc = await nats.connect(
                servers=[settings.NATS_URL],
                name="auth-service",
                reconnect_time_wait=2,
                max_reconnect_attempts=60,
                connect_timeout=5,
            )
            self.js = self.nc.jetstream()
            self.is_connected = True
            logger.info("Connected to NATS server successfully.")

            # Ensure required JetStream streams exist
            await self.ensure_streams()
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to NATS at {settings.NATS_URL}: {e}")
            self.is_connected = False
            return False

    async def ensure_streams(self) -> None:
        """
        Declares or updates required JetStream streams:
        - UPLOADS: subjects ['upload.>']
        - ENGAGEMENT: subjects ['engagement.>']
        """
        if not self.js:
            return

        stream_definitions: List[Dict[str, Any]] = [
            {
                "name": settings.NATS_STREAM_UPLOADS,
                "subjects": [settings.NATS_SUBJECT_UPLOADS, "transcode.>"],
            },
            {
                "name": settings.NATS_STREAM_ENGAGEMENT,
                "subjects": [settings.NATS_SUBJECT_ENGAGEMENT],
            },
        ]

        for s_def in stream_definitions:
            name = s_def["name"]
            subjects = s_def["subjects"]
            try:
                # Check if stream already exists
                await self.js.stream_info(name)
                logger.info(f"JetStream stream '{name}' already exists.")
                try:
                    await self.js.update_stream(name=name, subjects=subjects)
                except Exception:
                    pass
            except Exception:
                # Create stream
                try:
                    await self.js.add_stream(
                        name=name,
                        subjects=subjects,
                        storage=StorageType.FILE,
                        retention=RetentionPolicy.LIMITS,
                    )
                    logger.info(f"Created JetStream stream '{name}' with subjects {subjects}")
                except Exception as create_err:
                    logger.warning(f"Could not create JetStream stream '{name}': {create_err}")

    async def publish(
        self,
        subject: str,
        payload: Union[Dict[str, Any], str, bytes],
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """
        Publishes a message to NATS JetStream and awaits publication acknowledgement.
        """
        if not self.is_connected or not self.js:
            connected = await self.connect()
            if not connected or not self.js:
                raise RuntimeError("NATS JetStream is not connected")

        if isinstance(payload, dict):
            data = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = payload

        ack = await self.js.publish(subject=subject, payload=data, headers=headers)
        logger.debug(f"Published message to '{subject}' (seq={ack.seq}, stream={ack.stream})")
        return ack

    async def check_health(self) -> bool:
        """
        Readiness check verifying NATS connection and JetStream responsiveness.
        """
        try:
            active_loop = asyncio.get_running_loop()
        except RuntimeError:
            active_loop = None

        current_loop = getattr(self.nc, "_loop", None)
        if (
            not self.is_connected
            or not self.nc
            or self.nc.is_closed
            or not current_loop
            or current_loop.is_closed()
            or (active_loop and current_loop != active_loop)
        ):
            # Attempt a single quick reconnect on current loop
            self.nc = None
            self.js = None
            self.is_connected = False
            connected = await self.connect()
            if not connected:
                return False

        try:
            # Flush connection roundtrip with 1-second timeout
            await self.nc.flush(timeout=1.0)
            return True
        except Exception as e:
            logger.warning(f"NATS health probe ping failed: {e}")
            return False

    async def close(self) -> None:
        """
        Gracefully drains and closes the NATS connection on application shutdown.
        """
        if self.nc and not self.nc.is_closed:
            logger.info("Closing NATS connection...")
            try:
                await self.nc.drain()
                await self.nc.close()
            except Exception as e:
                logger.warning(f"Error during NATS close: {e}")
            finally:
                self.is_connected = False
                self.nc = None
                self.js = None
                logger.info("NATS connection closed.")


event_bus = EventBus()
