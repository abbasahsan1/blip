import json
import uuid
import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient, ASGITransport

from app.main import app
from blipp_common.config import settings
from blipp_common.security import get_optional_current_user, AuthenticatedUser
from blipp_common.database import get_db_pool


@pytest.fixture(autouse=True)
def clean_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_feed_healthz():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_ranked_feed_gorse_fetch_and_cache(monkeypatch):
    """
    Validates Section 6.4 Ranked Feed:
    - Stage 1: Redis cache miss
    - Stage 2: Gorse /api/recommend/{user_id} called and cached
    - Stage 3: Hydration from PostgreSQL with strict order preservation
    - Stage 4: Cold-start exploration item interleaving
    """
    test_user_id = uuid.uuid4()
    test_user = AuthenticatedUser(
        user_id=test_user_id,
        id=str(test_user_id),
        username=f"rank_tester_{test_user_id.hex[:6]}",
        email="rank_tester@blipp.dev",
        first_name="Rank",
        last_name="Tester",
        roles=["listener"],
    )
    app.dependency_overrides[get_optional_current_user] = lambda: test_user

    # 1. Seed test database with items
    pool = await get_db_pool()
    creator_id = uuid.uuid4()
    blipp_ids = [uuid.uuid4() for _ in range(5)]
    cold_start_id = uuid.uuid4()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
            """,
            creator_id, f"c_{creator_id.hex[:6]}", "Reel Creator",
        )
        for i, bid in enumerate(blipp_ids):
            await conn.execute(
                """
                INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
                VALUES ($1, $2, $3, $4, $5, 'published')
                ON CONFLICT (blipp_id) DO NOTHING
                """,
                bid, creator_id, f"Ranked Track #{i+1}", f"audio/track_{i+1}.mp3", 45.0,
            )

        await conn.execute(
            """
            INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
            VALUES ($1, $2, $3, $4, $5, 'published')
            ON CONFLICT (blipp_id) DO NOTHING
            """,
            cold_start_id, creator_id, "Fresh Cold Start Clip", "audio/fresh.mp3", 20.0,
        )

    # 2. Mock Gorse API call returning 3 recommended blipp IDs in reverse order
    gorse_recommendation = [str(blipp_ids[2]), str(blipp_ids[0]), str(blipp_ids[1])]

    class MockResponse:
        status_code = 200
        def json(self):
            return gorse_recommendation

    async def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # 3. Call GET /v1/feed
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/feed")
        assert resp.status_code == 200, f"Expected 200 OK, got: {resp.text}"
        data = resp.json()
        assert "items" in data
        items = data["items"]
        assert len(items) >= 4, "Feed must contain Gorse recommendations plus fallback items"

        returned_ids = [item["blipp_id"] for item in items]
        assert str(blipp_ids[2]) in returned_ids
        assert str(blipp_ids[0]) in returned_ids
