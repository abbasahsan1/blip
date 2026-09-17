"""
T28: Duplicate-delivery idempotency tests for feed event handlers.

These tests verify that replaying the same engagement event N times produces
the same end state as a single delivery — the core idempotency invariant.

Tests use a real asyncpg connection to a test database when INTEGRATION_TEST=1,
otherwise they skip. The suite is designed to run in CI against a disposable DB.
"""

import asyncio
import os
import uuid
import pytest

INTEGRATION_TEST = os.environ.get("INTEGRATION_TEST") == "1"
DB_URL = os.environ.get(
    "FEED_DB_URL",
    "postgresql://keycloak:keycloak_secure_db_pass@localhost:5432/blipp_feed",
)


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def db_pool():
    import asyncpg
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
    yield pool
    await pool.close()


@pytest.fixture
async def clean_state(db_pool):
    """Truncate projection tables before each test for a clean slate."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            TRUNCATE TABLE
                feed_items,
                feed_item_stats,
                user_likes_projection,
                user_saves_projection,
                user_follows_projection
            RESTART IDENTITY CASCADE
            """
        )
    yield


@pytest.mark.skipif(not INTEGRATION_TEST, reason="Set INTEGRATION_TEST=1 to run")
@pytest.mark.asyncio
async def test_like_event_idempotency(db_pool, clean_state):
    """
    T28: Replaying engagement.like N times leaves likes_count == 1.
    Acceptance: event replayed 5 times → likes_count == 1, projection row count == 1.
    """
    from services.feed.app.event_handlers import handle_like_event

    user_id = uuid.uuid4()
    blipp_id = uuid.uuid4()

    # Seed a feed_item for the blipp
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feed_items (blipp_id, creator_id, audio_url, created_at)
            VALUES ($1, $2, 'http://test/audio.mp3', NOW())
            """,
            blipp_id, user_id,
        )

    like_event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "like",
        "user_id": str(user_id),
        "blipp_id": str(blipp_id),
    }

    # Deliver the same event 5 times (simulates at-least-once re-delivery)
    for _ in range(5):
        await handle_like_event(like_event, is_like=True)

    async with db_pool.acquire() as conn:
        likes_count = await conn.fetchval(
            "SELECT likes_count FROM feed_item_stats WHERE blipp_id = $1", blipp_id
        )
        projection_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_likes_projection WHERE blipp_id = $1 AND user_id = $2",
            blipp_id, user_id,
        )

    assert likes_count == 1, f"Expected likes_count=1 after 5 deliveries, got {likes_count}"
    assert projection_count == 1, f"Expected 1 projection row, got {projection_count}"


@pytest.mark.skipif(not INTEGRATION_TEST, reason="Set INTEGRATION_TEST=1 to run")
@pytest.mark.asyncio
async def test_save_event_idempotency(db_pool, clean_state):
    """
    T28: Replaying engagement.save N times leaves saves_count == 1.
    """
    from services.feed.app.event_handlers import handle_save_event

    user_id = uuid.uuid4()
    blipp_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feed_items (blipp_id, creator_id, audio_url, created_at)
            VALUES ($1, $2, 'http://test/audio.mp3', NOW())
            """,
            blipp_id, user_id,
        )

    save_event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "save",
        "user_id": str(user_id),
        "blipp_id": str(blipp_id),
    }

    for _ in range(5):
        await handle_save_event(save_event, is_save=True)

    async with db_pool.acquire() as conn:
        saves_count = await conn.fetchval(
            "SELECT saves_count FROM feed_item_stats WHERE blipp_id = $1", blipp_id
        ) or 0
        projection_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_saves_projection WHERE blipp_id = $1 AND user_id = $2",
            blipp_id, user_id,
        )

    assert saves_count == 1, f"Expected saves_count=1 after 5 deliveries, got {saves_count}"
    assert projection_count == 1, f"Expected 1 projection row, got {projection_count}"


@pytest.mark.skipif(not INTEGRATION_TEST, reason="Set INTEGRATION_TEST=1 to run")
@pytest.mark.asyncio
async def test_follow_event_idempotency(db_pool, clean_state):
    """
    T28: Replaying engagement.follow N times leaves exactly one projection row.
    """
    from services.feed.app.event_handlers import handle_follow_event

    follower_id = uuid.uuid4()
    followee_id = uuid.uuid4()

    follow_event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "follow",
        "user_id": str(follower_id),
        "target_user_id": str(followee_id),
    }

    for _ in range(5):
        await handle_follow_event(follow_event, is_follow=True)

    async with db_pool.acquire() as conn:
        projection_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM user_follows_projection
            WHERE follower_id = $1 AND followee_id = $2
            """,
            follower_id, followee_id,
        )

    assert projection_count == 1, f"Expected 1 follow projection row, got {projection_count}"


@pytest.mark.skipif(not INTEGRATION_TEST, reason="Set INTEGRATION_TEST=1 to run")
@pytest.mark.asyncio
async def test_blipp_published_idempotency(db_pool, clean_state):
    """
    T28: Replaying engagement.blipp.published N times produces exactly one feed_items row.
    """
    from services.feed.app.event_handlers import handle_blipp_published

    creator_id = uuid.uuid4()
    blipp_id = uuid.uuid4()

    published_event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "blipp.published",
        "blipp_id": str(blipp_id),
        "creator_id": str(creator_id),
        "title": "Test Blipp",
        "description": "Idempotency test",
        "audio_url": "http://test/audio.mp3",
        "audio_variants": {},
        "duration_seconds": 60.0,
        "author_username": "testuser",
        "author_display_name": "Test User",
        "author_avatar_url": None,
    }

    for _ in range(5):
        await handle_blipp_published(published_event)

    async with db_pool.acquire() as conn:
        row_count = await conn.fetchval(
            "SELECT COUNT(*) FROM feed_items WHERE blipp_id = $1", blipp_id
        )

    assert row_count == 1, f"Expected 1 feed_items row after 5 deliveries, got {row_count}"


@pytest.mark.skipif(not INTEGRATION_TEST, reason="Set INTEGRATION_TEST=1 to run")
@pytest.mark.asyncio
async def test_takedown_idempotency(db_pool, clean_state):
    """
    T28: Replaying content.takedown N times results in exactly one taken_down_at set.
    """
    from services.feed.app.event_handlers import handle_blipp_takedown

    creator_id = uuid.uuid4()
    blipp_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feed_items (blipp_id, creator_id, audio_url, created_at)
            VALUES ($1, $2, 'http://test/audio.mp3', NOW())
            """,
            blipp_id, creator_id,
        )

    takedown_event = {
        "event_id": str(uuid.uuid4()),
        "blipp_id": str(blipp_id),
        "reason": "test_moderation",
    }

    for _ in range(5):
        await handle_blipp_takedown(takedown_event)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT taken_down_at FROM feed_items WHERE blipp_id = $1", blipp_id
        )

    assert row is not None, "feed_items row should still exist (soft delete)"
    assert row["taken_down_at"] is not None, "taken_down_at should be set"
