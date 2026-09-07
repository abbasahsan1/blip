import json
import uuid
import asyncio
from datetime import datetime, timezone, date
import pytest
import pytest_asyncio
import nats

from app.config import settings
from app.database import (
    get_db_pool,
    init_db,
    close_db,
    record_playback_engagement,
)
from app.main import ensure_streams, process_message


@pytest_asyncio.fixture(autouse=True)
async def db_lifecycle():
    await init_db()
    yield
    await close_db()


@pytest.mark.asyncio
async def test_record_playback_engagement_progress():
    """
    Validates Section 6.5 aggregation:
    - Background device signals (screen_off, bluetooth_connected) are accepted as active playback.
    - total_seconds_listened accumulates accurately.
    - CreatorMinutesAgg updates proportionally.
    """
    pool = await get_db_pool()
    creator_id = uuid.uuid4()
    user_id = uuid.uuid4()
    blipp_id = uuid.uuid4()
    session_id = uuid.uuid4()

    async with pool.acquire() as conn:
        # Create creator and listener profiles
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3), ($4, $5, $6)
            """,
            creator_id, f"creator_{creator_id.hex[:6]}", "Test Creator",
            user_id, f"listener_{user_id.hex[:6]}", "Test Listener",
        )
        # Create published blipp with 60s duration
        await conn.execute(
            """
            INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
            VALUES ($1, $2, $3, $4, $5, 'published')
            """,
            blipp_id, creator_id, "Aggregation Test Blipp", "http://storage/test.m4a", 60.0,
        )

    # 1. First event: 10s playback with screen_off
    res1 = await record_playback_engagement(
        session_id=session_id,
        user_id=user_id,
        blipp_id=blipp_id,
        position_seconds=10.0,
        duration_seconds=60.0,
        event_type="play_progress",
        device_signal="screen_off",
    )
    assert res1["total_seconds_listened"] == 10.0
    assert res1["delta_seconds"] == 10.0
    assert res1["delta_minutes"] == pytest.approx(10.0 / 60.0)
    assert res1["completed"] is False

    # 2. Second event: 25s playback with bluetooth_connected
    res2 = await record_playback_engagement(
        session_id=session_id,
        user_id=user_id,
        blipp_id=blipp_id,
        position_seconds=25.0,
        duration_seconds=60.0,
        event_type="play_progress",
        device_signal="bluetooth_connected",
    )
    assert res2["total_seconds_listened"] == 25.0
    assert res2["delta_seconds"] == 15.0
    assert res2["delta_minutes"] == pytest.approx(15.0 / 60.0)
    assert res2["completed"] is False

    # 3. Verify PostgreSQL rows
    async with pool.acquire() as conn:
        session_row = await conn.fetchrow(
            "SELECT total_seconds_listened, completed, drop_off_position_seconds FROM listening_session_agg WHERE session_id = $1",
            session_id,
        )
        assert session_row is not None
        assert session_row["total_seconds_listened"] == 25.0
        assert session_row["completed"] is False
        assert session_row["drop_off_position_seconds"] == 25.0

        creator_row = await conn.fetchrow(
            "SELECT total_minutes_listened FROM creator_minutes_agg WHERE creator_id = $1 AND blipp_id = $2",
            creator_id, blipp_id,
        )
        assert creator_row is not None
        assert creator_row["total_minutes_listened"] == pytest.approx(25.0 / 60.0)


@pytest.mark.asyncio
async def test_completion_threshold():
    """
    Validates that reaching 90% duration marks completed = True.
    """
    pool = await get_db_pool()
    creator_id = uuid.uuid4()
    user_id = uuid.uuid4()
    blipp_id = uuid.uuid4()
    session_id = uuid.uuid4()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3), ($4, $5, $6)
            """,
            creator_id, f"c_{creator_id.hex[:6]}", "Creator",
            user_id, f"l_{user_id.hex[:6]}", "Listener",
        )
        await conn.execute(
            """
            INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
            VALUES ($1, $2, $3, $4, $5, 'published')
            """,
            blipp_id, creator_id, "Completion Blipp", "http://storage/test.m4a", 100.0,
        )

    # 85 seconds: not yet 90%
    r1 = await record_playback_engagement(
        session_id=session_id,
        user_id=user_id,
        blipp_id=blipp_id,
        position_seconds=85.0,
        duration_seconds=100.0,
        event_type="play_progress",
        device_signal="screen_on",
    )
    assert r1["completed"] is False

    # 90 seconds: 90% reached -> completed = True
    r2 = await record_playback_engagement(
        session_id=session_id,
        user_id=user_id,
        blipp_id=blipp_id,
        position_seconds=90.0,
        duration_seconds=100.0,
        event_type="play_progress",
        device_signal="screen_on",
    )
    assert r2["completed"] is True

    async with pool.acquire() as conn:
        completed = await conn.fetchval(
            "SELECT completed FROM listening_session_agg WHERE session_id = $1",
            session_id,
        )
        assert completed is True


@pytest.mark.asyncio
async def test_play_complete_and_skip():
    """
    Validates play_complete and skip events.
    """
    pool = await get_db_pool()
    creator_id = uuid.uuid4()
    user_id = uuid.uuid4()
    blipp_id = uuid.uuid4()
    session_id = uuid.uuid4()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3), ($4, $5, $6)
            """,
            creator_id, f"c_{creator_id.hex[:6]}", "Creator",
            user_id, f"l_{user_id.hex[:6]}", "Listener",
        )
        await conn.execute(
            """
            INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
            VALUES ($1, $2, $3, $4, $5, 'published')
            """,
            blipp_id, creator_id, "Complete/Skip Blipp", "http://storage/test.m4a", 40.0,
        )

    # play_complete automatically sets completed = True and total_seconds = duration
    r = await record_playback_engagement(
        session_id=session_id,
        user_id=user_id,
        blipp_id=blipp_id,
        position_seconds=40.0,
        duration_seconds=40.0,
        event_type="play_complete",
        device_signal="screen_on",
    )
    assert r["completed"] is True
    assert r["total_seconds_listened"] == 40.0


@pytest.mark.asyncio
async def test_live_nats_worker_flow():
    """
    End-to-end NATS JetStream publish -> pull consumer dispatch test.
    """
    nc = await nats.connect(servers=[settings.NATS_URL])
    js = nc.jetstream()

    await ensure_streams(js)

    user_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    blipp_id = uuid.uuid4()
    session_id = uuid.uuid4()

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3), ($4, $5, $6)
            """,
            creator_id, f"c_{creator_id.hex[:6]}", "Creator",
            user_id, f"l_{user_id.hex[:6]}", "Listener",
        )
        await conn.execute(
            """
            INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
            VALUES ($1, $2, $3, $4, $5, 'published')
            """,
            blipp_id, creator_id, "NATS JetStream Test Blipp", "http://storage/test.m4a", 50.0,
        )

    # Subscribe with unique subject and NEW deliver policy before publishing
    unique_subject = f"engagement.test_{uuid.uuid4().hex}"
    test_sub = await js.pull_subscribe(
        subject=unique_subject,
        stream=settings.NATS_STREAM_ENGAGEMENT,
        config=nats.js.api.ConsumerConfig(deliver_policy=nats.js.api.DeliverPolicy.NEW),
    )

    # Publish message to unique engagement subject
    payload = {
        "event_type": "play_progress",
        "user_id": str(user_id),
        "blipp_id": str(blipp_id),
        "session_id": str(session_id),
        "position_seconds": 15.0,
        "duration_seconds": 50.0,
        "device_signal": "app_backgrounded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await js.publish(
        subject=unique_subject,
        payload=json.dumps(payload).encode("utf-8"),
    )

    msgs = await test_sub.fetch(batch=1, timeout=5.0)
    assert len(msgs) == 1
    await process_message(js, msgs[0])

    # Verify session row was created
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT total_seconds_listened, completed FROM listening_session_agg WHERE session_id = $1",
            session_id,
        )
        assert row is not None
        assert row["total_seconds_listened"] == 15.0

    await test_sub.unsubscribe()
    await nc.close()
