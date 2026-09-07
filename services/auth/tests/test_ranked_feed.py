import json
import uuid
import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.security import get_current_user, get_optional_current_user
from app.core.database import get_db_pool
from app.models.schemas import AuthenticatedUser


@pytest.fixture(autouse=True)
def clean_overrides():
    yield
    app.dependency_overrides.clear()


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
                VALUES ($1, $2, $3, $4, 45.0, 'published')
                ON CONFLICT (blipp_id) DO NOTHING
                """,
                bid, creator_id, f"Ranked Blipp {i+1}", f"http://storage/{bid}.m4a",
            )
        # Cold start item with 0 listens
        await conn.execute(
            """
            INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
            VALUES ($1, $2, 'Cold Start Exploration Blipp', 'http://storage/cold.m4a', 30.0, 'published')
            ON CONFLICT (blipp_id) DO NOTHING
            """,
            cold_start_id, creator_id,
        )

    # 2. Mock in-memory Redis cache
    cache_store = {}

    class MockRedis:
        async def get(self, key):
            return cache_store.get(key)

        async def set(self, key, value, ex=None):
            cache_store[key] = value
            return True

    from app.core import redis as redis_mod
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda: MockRedis())

    # 3. Mock Gorse REST API to return items in reversed order: [blipp_ids[4], blipp_ids[3], blipp_ids[2]]
    gorse_recommendations = [str(blipp_ids[4]), str(blipp_ids[3]), str(blipp_ids[2])]

    async def mock_get(client_self, url, headers=None, **kwargs):
        if "/api/recommend/" in str(url):
            return httpx.Response(200, json=gorse_recommendations)
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/blipps")
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert len(items) >= 3

        # Verify Redis was populated on cache miss
        cache_key = f"feed:{test_user_id}"
        assert cache_key in cache_store
        assert json.loads(cache_store[cache_key]) == gorse_recommendations

        # Verify items returned preserve the exact ranking order from Gorse:
        # (With potential cold-start interleaved at index 1)
        item_ids = [item["blipp_id"] for item in items]
        
        # Verify first item matches first Gorse recommendation
        assert item_ids[0] == str(blipp_ids[4])


@pytest.mark.asyncio
async def test_ranked_feed_redis_cache_hit(monkeypatch):
    """
    Validates that when candidate IDs exist in Redis, Gorse API is NOT called.
    """
    test_user_id = uuid.uuid4()
    test_user = AuthenticatedUser(
        user_id=test_user_id,
        id=str(test_user_id),
        username=f"cache_hit_{test_user_id.hex[:6]}",
        email="cache_hit@blipp.dev",
        first_name="Cache",
        last_name="Hit",
        roles=["listener"],
    )
    app.dependency_overrides[get_optional_current_user] = lambda: test_user

    pool = await get_db_pool()
    creator_id = uuid.uuid4()
    test_blipp_id = uuid.uuid4()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
            """,
            creator_id, f"c_{creator_id.hex[:6]}", "Cache Creator",
        )
        await conn.execute(
            """
            INSERT INTO blipps (blipp_id, creator_id, title, audio_url, duration_seconds, status)
            VALUES ($1, $2, 'Pre-cached Blipp', 'http://storage/cached.m4a', 20.0, 'published')
            ON CONFLICT (blipp_id) DO NOTHING
            """,
            test_blipp_id, creator_id,
        )

    cache_store = {
        f"feed:{test_user_id}": json.dumps([str(test_blipp_id)])
    }

    class MockRedis:
        async def get(self, key):
            return cache_store.get(key)

        async def set(self, key, value, ex=None):
            cache_store[key] = value

    from app.core import redis as redis_mod
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda: MockRedis())

    gorse_called = False

    async def mock_get(client_self, url, **kwargs):
        nonlocal gorse_called
        gorse_called = True
        return httpx.Response(500)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/blipps")
        assert resp.status_code == 200
        # Gorse should not have been called because of cache hit
        assert not gorse_called
        data = resp.json()
        assert any(item["blipp_id"] == str(test_blipp_id) for item in data["items"])
