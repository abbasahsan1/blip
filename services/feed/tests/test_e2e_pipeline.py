"""
End-to-End Pipeline Integration Test

Tests the full upload -> NATS -> transcode -> content -> NATS -> feed projection -> GET /feed path.

Requirements:
  - INTEGRATION_TEST=1 env var
  - All services running (content-ingest, transcode-worker, feed-service)
  - Real Postgres, NATS JetStream, Redis, MinIO

Run with:
    INTEGRATION_TEST=1 pytest services/feed/tests/test_e2e_pipeline.py -v -s
"""
import asyncio
import json
import os
import uuid
import pytest
import pytest_asyncio

pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEGRATION_TEST"),
    reason="Set INTEGRATION_TEST=1 to run real-infra e2e tests",
)

CONTENT_INGEST_URL = os.environ.get("CONTENT_INGEST_URL", os.environ.get("GATEWAY_URL", "http://localhost:8419"))
FEED_URL = os.environ.get("FEED_URL", os.environ.get("GATEWAY_URL", "http://localhost:8419"))


@pytest_asyncio.fixture
async def auth_token():
    """
    Obtain a valid auth token from Keycloak for the test user.
    Requires KEYCLOAK_TEST_USER and KEYCLOAK_TEST_PASSWORD env vars.
    """
    import httpx
    from blipp_common.config import settings

    user = os.environ.get("KEYCLOAK_TEST_USER", "testuser")
    password = os.environ.get("KEYCLOAK_TEST_PASSWORD", "TestPassword123!")
    keycloak_base = os.environ.get("KEYCLOAK_URL", settings.KEYCLOAK_URL).rstrip("/")
    token_url = f"{keycloak_base}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data={
            "grant_type": "password",
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
            "username": user,
            "password": password,
        })

    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def feed_db():
    """Acquire the feed service DB pool for assertions if available."""
    try:
        from blipp_common.database import get_db_pool, init_db_pool
        await init_db_pool()
        return await get_db_pool()
    except Exception:
        return None


@pytest.mark.asyncio
async def test_upload_appears_in_feed(auth_token, feed_db):
    """
    Full pipeline test:
    1. POST /v1/uploads with a real audio file
    2. Poll upload status until published (transcode -> moderation -> publish)
    3. Assert the blipp appears in GET /v1/feed
    4. Assert the audio variant URL is reachable and streams real audio bytes

    This validates the complete event-driven path without any mocking.
    """
    import httpx

    headers = {"Authorization": f"Bearer {auth_token}"}

    # In a real CI environment, use a fixture audio file
    test_audio_path = os.environ.get(
        "TEST_AUDIO_FILE",
        "/home/ali/blipp-dev/test_audio.mp3"
    )

    assert os.path.exists(test_audio_path), (
        f"Test audio file not found at {test_audio_path}. "
        "Set TEST_AUDIO_FILE env var to a valid audio file path."
    )

    blipp_title = f"E2E Pipeline Test {uuid.uuid4()}"

    # Step 1: Upload
    async with httpx.AsyncClient(timeout=30.0) as client:
        with open(test_audio_path, "rb") as audio_file:
            resp = await client.post(
                f"{CONTENT_INGEST_URL}/v1/uploads",
                headers=headers,
                files={"file": ("test_audio.mp3", audio_file, "audio/mpeg")},
                data={"upload_type": "audio", "title": blipp_title},
            )

    assert resp.status_code == 202, f"Upload failed: {resp.status_code} {resp.text}"
    upload_data = resp.json()
    upload_id = upload_data["upload_id"]
    assert upload_id, "No upload_id in response"

    # Step 2: Poll upload status until published (up to 120s for transcode)
    final_status = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(60):  # 60 * 2s = 120s max
            await asyncio.sleep(2.0)
            status_resp = await client.get(
                f"{CONTENT_INGEST_URL}/v1/uploads/{upload_id}",
                headers=headers,
            )
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                final_status = status_data.get("processing_status")
                if final_status == "published":
                    break
                if final_status in ("failed", "rejected"):
                    pytest.fail(f"Upload {upload_id} processing failed: {status_data}")

    assert final_status == "published", (
        f"Upload {upload_id} did not reach published state within 120s. "
        f"Final status: {final_status}"
    )

    # Step 3: Assert blipp appears in feed
    blipp_in_feed = False
    matched_item = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(10):
            await asyncio.sleep(1.0)
            feed_resp = await client.get(
                f"{FEED_URL}/v1/feed",
                headers=headers,
            )
            if feed_resp.status_code == 200:
                feed_data = feed_resp.json()
                items = feed_data.get("items", [])
                for item in items:
                    if item.get("title") == blipp_title:
                        blipp_in_feed = True
                        matched_item = item
                        break
                if blipp_in_feed:
                    break

    assert blipp_in_feed and matched_item is not None, (
        f"Blipp with title '{blipp_title}' did not appear in GET /v1/feed within 10s "
        "after reaching published state. Check feed projection consumer."
    )

    # Step 4: Playback assertion - fetch audio_url and verify playable bytes
    audio_url = matched_item.get("audio_url")
    assert audio_url, f"Feed item missing audio_url: {matched_item}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        audio_resp = await client.get(audio_url)
        assert audio_resp.status_code in (200, 206), (
            f"Failed to fetch audio from {audio_url}: {audio_resp.status_code} {audio_resp.text}"
        )
        assert len(audio_resp.content) > 0, "Audio response body is empty"
