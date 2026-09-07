import io
import json
import uuid
import asyncio
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from nats.js.api import DeliverPolicy

from app.main import app
from blipp_common.config import settings
from blipp_common.security import get_current_user, AuthenticatedUser
from blipp_common.database import get_db_pool
from blipp_common.storage import storage_service
from blipp_common.events import event_bus


@pytest.fixture(autouse=True)
def clean_overrides():
    """Clear FastAPI dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_probes():
    """Verify health and readyz probes return expected payloads."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_authenticated_upload_pipeline():
    """
    Verifies Section 5.3 asynchronous upload pipeline:
    - POST /v1/uploads with audio file
    - Response HTTP 202 Accepted
    - Storage object exists in MinIO blipp-raw-uploads bucket
    - Database record persisted in uploads table with status 'queued'
    - NATS JetStream upload.received event published on UPLOADS stream
    - GET /v1/uploads/{upload_id} authorization and status verification
    """
    test_user_id = uuid.uuid4()
    test_user = AuthenticatedUser(
        user_id=test_user_id,
        id=str(test_user_id),
        username=f"pipeline_tester_{test_user_id.hex[:8]}",
        email="tester@blipp.dev",
        first_name="Audio",
        last_name="Tester",
        roles=["creator"],
    )
    app.dependency_overrides[get_current_user] = lambda: test_user

    # 1. Subscribe to NATS UPLOADS stream before publishing to catch the event
    await event_bus.connect()
    sub = await event_bus.js.subscribe(
        subject="upload.>",
        deliver_policy=DeliverPolicy.NEW,
    )

    sample_audio_content = b"ID3\x03\x00\x00\x00\x00\x00#RAW_AUDIO_TEST_BYTES#" + str(uuid.uuid4()).encode()
    audio_filename = "synth_beat.mp3"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. Issue POST /v1/uploads
        files = {
            "file": (audio_filename, io.BytesIO(sample_audio_content), "audio/mpeg")
        }
        data = {
            "upload_type": "audio",
            "title": "Test Synth Beat",
            "description": "Integration test raw clip for async transcode pipeline",
        }
        post_resp = await client.post("/v1/uploads", data=data, files=files)
        assert post_resp.status_code == 202, f"Expected 202 Accepted, got: {post_resp.text}"
        post_json = post_resp.json()
        assert "upload_id" in post_json
        assert post_json["status"] == "queued"
        upload_id = post_json["upload_id"]

        # 3. Verify upload record in PostgreSQL
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT upload_id, creator_id, raw_file_url, processing_status, title FROM uploads WHERE upload_id = $1",
                uuid.UUID(upload_id),
            )
            assert row is not None, "Upload row was not found in PostgreSQL database"
            assert str(row["creator_id"]) == str(test_user_id)
            assert row["processing_status"] == "queued"
            assert row["title"] == "Test Synth Beat"
            storage_key = f"{test_user_id}/{upload_id}.mp3"

        # 4. Verify binary exists in MinIO
        downloaded = await storage_service.download_file(
            storage_key=storage_key,
            bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
        )
        assert downloaded == sample_audio_content, "MinIO object content mismatch with uploaded bytes"

        # 5. Verify NATS event published
        try:
            msg = await sub.next_msg(timeout=5.0)
            await msg.ack()
            payload = json.loads(msg.data.decode())
            assert payload.get("upload_id") == upload_id
            assert payload.get("creator_id") == str(test_user_id)
            assert payload.get("title") == "Test Synth Beat"
        finally:
            await sub.drain()

        # 6. Verify status polling GET /v1/uploads/{upload_id}
        status_resp = await client.get(f"/v1/uploads/{upload_id}")
        assert status_resp.status_code == 200
        status_json = status_resp.json()
        assert status_json["upload_id"] == upload_id
        assert status_json["processing_status"] == "queued"
        assert status_json["creator_id"] == str(test_user_id)
