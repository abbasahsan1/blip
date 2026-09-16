import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

import asyncpg

from blipp_common.events import event_bus

logger = logging.getLogger("blipp_common.outbox")

OUTBOX_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_events_unpublished 
    ON outbox_events (created_at) 
    WHERE published_at IS NULL;
"""


async def record_outbox_event(
    conn: asyncpg.Connection,
    subject: str,
    payload: Dict[str, Any],
    event_id: Optional[uuid.UUID] = None,
) -> uuid.UUID:
    """
    Inserts an event into the local transactional outbox table within the caller's transaction.
    Guarantees atomicity between domain state mutation and event recording.
    """
    eid = event_id or uuid.uuid4()
    payload_json = json.dumps(payload, default=str)
    await conn.execute(
        """
        INSERT INTO outbox_events (id, subject, payload)
        VALUES ($1, $2, $3::jsonb)
        """,
        eid,
        subject,
        payload_json,
    )
    return eid


_outbox_running = True


def stop_outbox_publisher() -> None:
    global _outbox_running
    _outbox_running = False


async def run_outbox_publisher(
    pool: asyncpg.Pool,
    service_name: str = "outbox-publisher",
    poll_interval_seconds: float = 0.5,
) -> None:
    """
    Background worker that continuously drains unpublished outbox events and
    publishes them to NATS JetStream with retries and exponential backoff.
    """
    global _outbox_running
    logger.info(f"Starting outbox publisher for {service_name}...")

    # Ensure outbox table exists in this service's database
    try:
        async with pool.acquire() as conn:
            await conn.execute(OUTBOX_TABLE_SQL)
    except Exception as e:
        logger.warning(f"Note creating outbox table: {e}")

    while _outbox_running:
        try:
            if not event_bus.is_connected or not event_bus.js:
                await asyncio.sleep(1.0)
                continue

            async with pool.acquire() as conn:
                async with conn.transaction():
                    rows = await conn.fetch(
                        """
                        SELECT id, subject, payload, retry_count
                        FROM outbox_events
                        WHERE published_at IS NULL
                        ORDER BY created_at ASC
                        LIMIT 50
                        FOR UPDATE SKIP LOCKED
                        """
                    )

                    for row in rows:
                        event_id = row["id"]
                        subject = row["subject"]
                        payload_data = row["payload"]
                        if isinstance(payload_data, str):
                            try:
                                payload_dict = json.loads(payload_data)
                            except Exception:
                                payload_dict = {"raw": payload_data}
                        else:
                            payload_dict = payload_data

                        try:
                            # Deliver to NATS JetStream
                            await event_bus.publish(
                                subject=subject,
                                payload=payload_dict,
                            )
                            # Mark published
                            await conn.execute(
                                """
                                UPDATE outbox_events
                                SET published_at = CURRENT_TIMESTAMP
                                WHERE id = $1
                                """,
                                event_id,
                            )
                            logger.debug(f"Outbox published event {event_id} to '{subject}'")
                        except Exception as pub_err:
                            logger.warning(
                                f"Failed to publish outbox event {event_id} to '{subject}': {pub_err}"
                            )
                            await conn.execute(
                                """
                                UPDATE outbox_events
                                SET retry_count = retry_count + 1,
                                    last_error = $2
                                WHERE id = $1
                                """,
                                event_id,
                                str(pub_err),
                            )

            await asyncio.sleep(poll_interval_seconds)

        except asyncio.CancelledError:
            break
        except Exception as loop_err:
            logger.error(f"Error in outbox publisher loop: {loop_err}")
            await asyncio.sleep(1.0)

    logger.info(f"Outbox publisher for {service_name} stopped.")


__all__ = [
    "OUTBOX_TABLE_SQL",
    "record_outbox_event",
    "run_outbox_publisher",
    "stop_outbox_publisher",
]
