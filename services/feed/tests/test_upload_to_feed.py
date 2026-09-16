import uuid
import pytest
import json
from datetime import datetime, timezone
import asyncio

from httpx import AsyncClient

from blipp_common.config import settings
from blipp_common.database import get_db_pool
from app.main import app
from app.event_handlers import handle_blipp_published

@pytest.fixture
async def setup_db():
    pool = await get_db_pool()
    # Ensure test environment creates tables
    from blipp_common.database import init_db_pool
    await init_db_pool()

    yield pool

    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_items")
        await conn.execute("DELETE FROM users_profile")

@pytest.mark.asyncio
async def test_upload_to_feed_projection(setup_db):
    """
    Test that an engagement.blipp.published event populates the feed projection 
    and that the feed API returns the projected blipp correctly.
    """
    pool = setup_db

    # 1. Simulate user creation (this would usually be handled by auth/profiles)
    creator_id = uuid.uuid4()
    blipp_id = uuid.uuid4()
    
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3)
            """,
            creator_id, "testuser", "Test User"
        )

    # 2. Simulate the transcode -> content_ingest -> publication flow 
    # by directly calling the feed event handler with the expected payload.
    published_payload = {
        "blipp_id": str(blipp_id),
        "creator_id": str(creator_id),
        "title": "My Awesome Test Audio",
        "description": "Integration testing is fun",
        "audio_url": f"s3://bucket/{creator_id}/{blipp_id}.mp3",
        "duration_seconds": 12.5,
        "published_at": datetime.now(timezone.utc).isoformat()
    }

    # Simulate the Feed consumer picking up the NATS event
    await handle_blipp_published(published_payload)

    # 3. Verify it exists in the new `feed_items` table
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM feed_items WHERE blipp_id = $1", blipp_id)
        assert row is not None, "Feed projection failed to insert into feed_items"
        assert row["title"] == "My Awesome Test Audio"
        assert row["duration_seconds"] == 12.5
        assert row["author_username"] == "testuser"

    # 4. Request the feed from the API and verify it uses the projection
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Note: Depending on the feed logic, it might require a token, 
        # but the feed endpoint is usually open or accepts optional auth.
        response = await client.get("/v1/feed")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        
        # Verify our blipp is in the feed
        items = data["items"]
        assert len(items) > 0
        
        # Find our blipp
        my_blipp = next((item for item in items if item["blipp_id"] == str(blipp_id)), None)
        assert my_blipp is not None, "Blipp not found in feed response"
        assert my_blipp["title"] == "My Awesome Test Audio"
        assert my_blipp["duration_seconds"] == 12.5
        assert my_blipp["username"] == "testuser"
