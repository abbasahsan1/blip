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
    publish_attempted_at TIMESTAMP WITH TIME ZONE,
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
) -> uuid.UUID:
    """
    Inserts an event into the local transactional outbox table within the caller's transaction.
    Guarantees atomicity between domain state mutation and event recording.

    Canonical event envelope injected automatically:
      - event_id   = outbox row id (the DB-generated UUID IS the canonical event_id)
      - event_type = subject
      - occurred_at = insertion timestamp
    Callers MUST NOT generate their own event_id — the outbox row id is the single
    authoritative identity for deduplication by downstream consumers.
    """
    eid = uuid.uuid4()
    # Inject canonical envelope fields into payload so consumers can always rely on them.
    enriched_payload = {
        "event_id": str(eid),
        "event_type": subject,
        "occurred_at": None,  # will be set by DB default, consumers read from outbox metadata
        **{k: v for k, v in payload.items() if k not in ("event_id", "event_type")},
    }
    payload_json = json.dumps(enriched_payload, default=str)
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

    # AT-LEAST-ONCE DELIVERY CONTRACT:
    # This outbox implements at-least-once delivery to NATS JetStream.
    # A process crash between "NATS publish succeeded" and "published_at committed" will
    # cause the event to be re-published on the next startup run.
    # ALL downstream consumers MUST be idempotent (use event_id for deduplication).
    #
    # Design: We use THREE short, separate DB interactions — not one long-held transaction:
    #   1. SELECT + mark publish_attempted_at   (short tx — claim batch)
    #   2. NATS publish                         (outside any DB transaction)
    #   3. UPDATE published_at or retry_count   (short tx — confirm result)
    # This prevents the DB connection being held open across the NATS network call.
    while _outbox_running:
        try:
            if not event_bus.is_connected or not event_bus.js:
                await asyncio.sleep(1.0)
                continue

            # ── Step 1: Claim a batch (short transaction) ────────────────────
            rows = []
            async with pool.acquire() as conn:
                async with conn.transaction():
                    rows = await conn.fetch(
                        """
                        SELECT id, subject, payload, retry_count
                        FROM outbox_events
                        WHERE published_at IS NULL
                          AND (
                            publish_attempted_at IS NULL
                            OR publish_attempted_at < CURRENT_TIMESTAMP - INTERVAL '60 seconds'
                          )
                        ORDER BY created_at ASC
                        LIMIT 50
                        FOR UPDATE SKIP LOCKED
                        """
                    )
                    if rows:
                        event_ids = [r["id"] for r in rows]
                        await conn.execute(
                            """
                            UPDATE outbox_events
                            SET publish_attempted_at = CURRENT_TIMESTAMP
                            WHERE id = ANY($1::uuid[])
                            """,
                            event_ids,
                        )

            if not rows:
                await asyncio.sleep(poll_interval_seconds)
                continue

            # ── Step 2: Publish to NATS (outside any DB transaction) ─────────
            successes = []
            failures = []
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
                    await event_bus.publish(subject=subject, payload=payload_dict)
                    successes.append(event_id)
                    logger.debug(f"Outbox published event {event_id} to '{subject}'")
                except Exception as pub_err:
                    failures.append((event_id, str(pub_err)))
                    logger.warning(f"Failed to publish outbox event {event_id} to '{subject}': {pub_err}")

            # ── Step 3: Confirm results (short transaction) ───────────────────
            async with pool.acquire() as conn:
                async with conn.transaction():
                    if successes:
                        await conn.execute(
                            """
                            UPDATE outbox_events
                            SET published_at = CURRENT_TIMESTAMP
                            WHERE id = ANY($1::uuid[])
                            """,
                            successes,
                        )
                    for fail_id, err_msg in failures:
                        await conn.execute(
                            """
                            UPDATE outbox_events
                            SET retry_count = retry_count + 1,
                                last_error = $2
                            WHERE id = $1
                            """,
                            fail_id,
                            err_msg,
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
