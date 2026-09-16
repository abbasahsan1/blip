"""
Feed Integration Test — upload-to-feed projection via real NATS JetStream.

Marked with @pytest.mark.integration — requires:
  - INTEGRATION_TEST=1 environment variable
  - Running Postgres (POSTGRES_* env vars)
  - Running NATS JetStream (NATS_URL env var)

Run with:
    INTEGRATION_TEST=1 pytest services/feed/tests/test_upload_to_feed.py -v
"""
import asyncio
import json
import os
import uuid
import pytest
from datetime import datetime, timezone

# Skip entire module if not in integration mode
pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEGRATION_TEST"),
    reason="Set INTEGRATION_TEST=1 to run real-infra integration tests",
)


@pytest.fixture
async def db_pool():
    """Acquire a real Postgres pool for the feed service database."""
    from blipp_common.database import get_db_pool, init_db_pool
    await init_db_pool()
    pool = await get_db_pool()
    yield pool
    # Cleanup: remove test data
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_items WHERE title LIKE 'IntegTest:%'")
        await conn.execute("DELETE FROM feed_item_stats WHERE blipp_id IN (SELECT blipp_id FROM feed_items WHERE title LIKE 'IntegTest:%')")


@pytest.fixture
async def nats_js():
    """Connect to real NATS JetStream."""
    import nats as nats_lib
    from blipp_common.config import settings
    nc = await nats_lib.connect(servers=[settings.NATS_URL])
    js = nc.jetstream()
    yield js
    await nc.drain()
    await nc.close()


@pytest.mark.asyncio
async def test_upload_to_feed_via_nats(db_pool, nats_js):
    """
    Real integration test: publish a content.blipp.published event via NATS JetStream
    and assert the Feed projection consumer picks it up and the item appears in feed_items.

    This tests the actual event-driven path:
      publish NATS event -> feed event_handlers consumer -> feed_items DB row
    """
    blipp_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    published_payload = {
        "blipp_id": str(blipp_id),
        "creator_id": str(creator_id),
        "title": f"IntegTest: Feed Projection {blipp_id}",
        "description": "Integration test blipp",
        "audio_url": f"s3://blipp-audio-variants/{creator_id}/{blipp_id}/high.m4a",
        "audio_variants": {
            "low": f"s3://blipp-audio-variants/{creator_id}/{blipp_id}/low.m4a",
            "standard": f"s3://blipp-audio-variants/{creator_id}/{blipp_id}/standard.m4a",
            "high": f"s3://blipp-audio-variants/{creator_id}/{blipp_id}/high.m4a",
        },
        "duration_seconds": 42.5,
        "author_username": "integtest_user",
        "author_display_name": "Integration Test User",
        "author_avatar_url": None,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }

    # Publish via NATS JetStream — the feed service's event consumer should pick this up
    await nats_js.publish(
        subject="content.blipp.published",
        payload=json.dumps(published_payload).encode("utf-8"),
    )

    # Poll the feed_items table for up to 10 seconds waiting for the projection
    row = None
    for _ in range(20):
        await asyncio.sleep(0.5)
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM feed_items WHERE blipp_id = $1", blipp_id
            )
        if row is not None:
            break

    assert row is not None, (
        f"Feed projection was not created within 10s for blipp {blipp_id}. "
        "Ensure the feed service event consumer is running and subscribed to content.blipp.published."
    )
    assert row["title"] == f"IntegTest: Feed Projection {blipp_id}"
    assert float(row["duration_seconds"]) == 42.5
    assert row["author_username"] == "integtest_user"
    assert row["creator_id"] == creator_id


@pytest.mark.asyncio
async def test_like_idempotency(db_pool):
    """
    Replay the same engagement.like event N times and assert likes_count remains 1.
    Tests T3 fix: idempotent like projection.
    """
    from app.event_handlers import handle_like_event

    blipp_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Seed a feed_item so stats row can be created
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feed_items (blipp_id, creator_id, title, audio_url, duration_seconds,
                                   author_username, author_display_name)
            VALUES ($1, $2, $3, $4, 1.0, 'user', 'User')
            ON CONFLICT (blipp_id) DO NOTHING
            """,
            blipp_id, user_id, f"IntegTest: Like Idempotency {blipp_id}",
            "s3://bucket/test.m4a",
        )

    like_payload = {"user_id": str(user_id), "blipp_id": str(blipp_id)}

    # Replay the same like event 5 times
    for _ in range(5):
        await handle_like_event(like_payload, is_like=True)

    async with db_pool.acquire() as conn:
        stats = await conn.fetchrow(
            "SELECT likes_count FROM feed_item_stats WHERE blipp_id = $1", blipp_id
        )

    assert stats is not None, "feed_item_stats row not created"
    assert stats["likes_count"] == 1, (
        f"Expected likes_count=1 after 5 replays, got {stats['likes_count']}. "
        "T3 idempotency fix may not be working."
    )

    # Cleanup
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_item_stats WHERE blipp_id = $1", blipp_id)
        await conn.execute("DELETE FROM user_likes_projection WHERE blipp_id = $1", blipp_id)
        await conn.execute("DELETE FROM feed_items WHERE blipp_id = $1", blipp_id)
