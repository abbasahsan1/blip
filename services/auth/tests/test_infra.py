import asyncio
import json
import uuid
import pytest
import nats
from nats.js.api import ConsumerConfig, DeliverPolicy

from app.core.config import settings
from app.core.storage import storage_service
from app.core.events import event_bus
from app.main import readiness_check


@pytest.mark.asyncio
async def test_minio_storage_write_read():
    """
    Verifies that files can be written to and read from MinIO S3 object storage.
    """
    test_id = str(uuid.uuid4())
    test_key = f"test-audio/{test_id}.mp3"
    test_content = b"ID3\x03\x00\x00\x00\x00\x00#AUDIO_BYTES#" + test_id.encode("utf-8")

    # 1. Upload file
    playback_url = await storage_service.upload_file(
        data=test_content,
        storage_key=test_key,
        bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
        content_type="audio/mpeg",
    )
    assert playback_url is not None
    assert test_key in playback_url or test_id in playback_url

    # 2. Download file and verify content
    downloaded_bytes = await storage_service.download_file(
        storage_key=test_key,
        bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
    )
    assert downloaded_bytes == test_content

    # 3. Presigned PUT verification
    presigned_put = storage_service.generate_presigned_put_url(
        storage_key=f"presigned/{test_id}.mp3",
        content_type="audio/mpeg",
        bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
    )
    assert presigned_put is not None
    assert "presigned" in presigned_put


@pytest.mark.asyncio
async def test_nats_jetstream_pub_sub():
    """
    Verifies that messages can be published to and consumed from NATS JetStream streams.
    """
    # 1. Ensure event_bus is connected and streams declared
    connected = await event_bus.connect()
    assert connected is True
    assert event_bus.js is not None

    test_event_id = str(uuid.uuid4())
    subject = "upload.created"
    test_payload = {
        "event_id": test_event_id,
        "type": "audio.uploaded",
        "creator_id": str(uuid.uuid4()),
        "storage_key": f"raw/{test_event_id}.mp3",
    }

    # 2. Subscribe to subject using ephemeral JetStream subscription
    sub = await event_bus.js.subscribe(
        subject="upload.>",
        deliver_policy=DeliverPolicy.NEW,
    )

    # 3. Publish message
    ack = await event_bus.publish(
        subject=subject,
        payload=test_payload,
    )
    assert ack is not None
    assert ack.stream == settings.NATS_STREAM_UPLOADS

    # 4. Receive message and verify payload
    msg = await sub.next_msg(timeout=5.0)
    await msg.ack()
    received_data = json.loads(msg.data.decode("utf-8"))
    assert received_data.get("event_id") == test_event_id
    assert received_data.get("type") == "audio.uploaded"

    await sub.unsubscribe()
    await event_bus.close()


@pytest.mark.asyncio
async def test_readiness_probe():
    """
    Verifies the /readyz endpoint status returns healthy for DB, MinIO, and NATS.
    """
    resp = await readiness_check()
    assert resp.status_code == 200
    body = json.loads(resp.body.decode("utf-8"))
    assert body.get("status") == "ready"
    components = body.get("components", {})
    assert components.get("database") == "healthy"
    assert components.get("storage") == "healthy"
    assert components.get("event_bus") == "healthy"
