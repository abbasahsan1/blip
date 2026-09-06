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
from app.core.config import settings
from app.core.security import get_current_user
from app.core.database import get_db_pool
from app.core.storage import storage_service
from app.core.events import event_bus
from app.models.schemas import AuthenticatedUser


@pytest.fixture(autouse=True)
def clean_overrides():
    """Clear FastAPI dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


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
        # 2. Perform POST /v1/uploads multipart upload
        files = {
            "file": (audio_filename, io.BytesIO(sample_audio_content), "audio/mpeg"),
        }
        data = {
            "upload_type": "audio",
            "title": "Synthetic Beat 120BPM",
            "description": "Electronic drum and bass loop",
        }

        resp = await client.post("/v1/uploads", files=files, data=data)
        assert resp.status_code == 202
        resp_data = resp.json()

        assert "upload_id" in resp_data
        upload_id = resp_data["upload_id"]
        assert resp_data.get("status") == "queued"
        assert "Upload received and queued for processing" in resp_data.get("message", "")

        # 3. Verify record in PostgreSQL database
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            db_row = await conn.fetchrow(
                """
                SELECT upload_id, creator_id, raw_file_url, upload_type, processing_status, title, description
                FROM uploads
                WHERE upload_id = $1
                """,
                uuid.UUID(upload_id),
            )

        assert db_row is not None
        assert str(db_row["creator_id"]) == str(test_user_id)
        assert db_row["processing_status"] == "queued"
        assert db_row["title"] == "Synthetic Beat 120BPM"
        assert db_row["description"] == "Electronic drum and bass loop"
        raw_file_url = db_row["raw_file_url"]
        assert settings.S3_BUCKET_RAW_UPLOADS in raw_file_url or upload_id in raw_file_url

        # 4. Verify file exists in MinIO bucket
        storage_key = storage_service.extract_storage_key(raw_file_url)
        downloaded_bytes = await storage_service.download_file(
            storage_key=storage_key,
            bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
        )
        assert downloaded_bytes == sample_audio_content

        # 5. Verify NATS upload.received event
        msg = await sub.next_msg(timeout=5.0)
        await msg.ack()
        event_payload = json.loads(msg.data.decode("utf-8"))
        assert event_payload.get("upload_id") == upload_id
        assert event_payload.get("creator_id") == str(test_user_id)
        assert event_payload.get("upload_type") == "audio"
        assert event_payload.get("title") == "Synthetic Beat 120BPM"
        assert event_payload.get("raw_file_url") == raw_file_url
        await sub.drain()

        # 6. Verify GET /v1/uploads/{upload_id} as owner
        status_resp = await client.get(f"/v1/uploads/{upload_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data.get("upload_id") == upload_id
        assert status_data.get("processing_status") in ("queued", "transcoding", "done")
        assert status_data.get("raw_file_url") == raw_file_url

        # 7. Verify GET /v1/uploads/{upload_id} as different user -> 403 Forbidden
        other_user = AuthenticatedUser(
            user_id=uuid.uuid4(),
            id=str(uuid.uuid4()),
            username="other_user",
            roles=["creator"],
        )
        app.dependency_overrides[get_current_user] = lambda: other_user
        forbidden_resp = await client.get(f"/v1/uploads/{upload_id}")
        assert forbidden_resp.status_code == 403
        err = forbidden_resp.json().get("error", {})
        assert err.get("code") == "FORBIDDEN"

        # 8. Verify GET /v1/uploads/{random_uuid} -> 404 Not Found
        not_found_resp = await client.get(f"/v1/uploads/{uuid.uuid4()}")
        assert not_found_resp.status_code == 404
        err = not_found_resp.json().get("error", {})
        assert err.get("code") == "NOT_FOUND"


@pytest.mark.asyncio
async def test_event_ingestion_single_and_batch():
    """
    Verifies Section 5.8 asynchronous telemetry event ingestion:
    - POST /v1/events accepts single and batch events
    - Returns HTTP 202 Accepted immediately with accepted count
    - Events published to NATS JetStream ENGAGEMENT stream under engagement.<event_type>
    """
    await event_bus.connect()
    sub = await event_bus.js.subscribe(
        subject="engagement.>",
        deliver_policy=DeliverPolicy.NEW,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Batch event payload (2 events)
        batch_events = [
            {
                "event_type": "play_progress",
                "user_id": str(uuid.uuid4()),
                "blipp_id": str(uuid.uuid4()),
                "session_id": str(uuid.uuid4()),
                "position_seconds": 15.5,
                "duration_seconds": 60.0,
                "device_signal": "bluetooth_connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "event_type": "like",
                "user_id": str(uuid.uuid4()),
                "blipp_id": str(uuid.uuid4()),
                "session_id": str(uuid.uuid4()),
                "position_seconds": 30.0,
                "duration_seconds": 60.0,
                "device_signal": "screen_on",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ]

        resp = await client.post("/v1/events", json=batch_events)
        assert resp.status_code == 202
        resp_data = resp.json()
        assert resp_data.get("status") == "accepted"
        assert resp_data.get("count") == 2

        # Verify both messages published to NATS
        received_types = set()
        for _ in range(2):
            msg = await sub.next_msg(timeout=5.0)
            await msg.ack()
            payload = json.loads(msg.data.decode("utf-8"))
            received_types.add(payload.get("event_type"))
        assert received_types == {"play_progress", "like"}

        # 2. Single event payload
        single_event = {
            "event_type": "share",
            "user_id": str(uuid.uuid4()),
            "blipp_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "position_seconds": 45.0,
            "duration_seconds": 60.0,
            "device_signal": "app_backgrounded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        resp_single = await client.post("/v1/events", json=single_event)
        assert resp_single.status_code == 202
        assert resp_single.json().get("status") == "accepted"
        assert resp_single.json().get("count") == 1

        msg = await sub.next_msg(timeout=5.0)
        await msg.ack()
        payload = json.loads(msg.data.decode("utf-8"))
        assert payload.get("event_type") == "share"
        assert payload.get("device_signal") == "app_backgrounded"

    await sub.drain()


@pytest.mark.asyncio
async def test_event_validation_errors():
    """
    Verifies input validation handling:
    - Invalid event_type returns HTTP 422
    - Missing required fields returns HTTP 422
    - Error response envelope matches standard structure
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid event_type
        invalid_type_event = {
            "event_type": "invalid_unsupported_action",
            "user_id": str(uuid.uuid4()),
            "blipp_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "position_seconds": 10.0,
            "duration_seconds": 30.0,
            "device_signal": "screen_on",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        resp = await client.post("/v1/events", json=invalid_type_event)
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "request_id" in data["error"]

        # 2. Missing required fields
        resp_empty = await client.post("/v1/events", json={})
        assert resp_empty.status_code == 422
        data_empty = resp_empty.json()
        assert "error" in data_empty
        assert data_empty["error"]["code"] == "VALIDATION_ERROR"
