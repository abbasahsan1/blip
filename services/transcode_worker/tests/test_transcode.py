import os
import json
import uuid
import asyncio
import tempfile
import subprocess
from datetime import datetime, timezone
import pytest
import pytest_asyncio
import nats
from nats.js.api import DeliverPolicy

from app.config import settings
from app.transcoder import probe_media, transcode_variants
from app.storage import storage_manager
from app.database import (
    get_db_pool,
    init_db,
    close_db,
    update_upload_status,
    get_upload,
    create_blipp,
)
from app.main import ensure_streams, process_message


def generate_test_audio(output_path: str, duration: int = 2) -> None:
    """Generate a minimal sine-wave audio file using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=1000:duration={duration}",
        output_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to generate test audio: {res.stderr}")


def generate_test_video(output_path: str, duration: int = 2) -> None:
    """Generate a minimal synthetic mp4 video with audio using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to generate test video: {res.stderr}")


@pytest.mark.asyncio
async def test_transcoder_direct_audio():
    """Unit test for FFmpeg transcoder with audio-only input."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_audio = os.path.join(tmpdir, "input.wav")
        out_dir = os.path.join(tmpdir, "variants")
        generate_test_audio(input_audio, duration=2)

        variants, duration, source_type = await transcode_variants(input_audio, out_dir)

        assert source_type == "direct_upload"
        assert 1.8 <= duration <= 2.2
        assert "low" in variants and "standard" in variants and "high" in variants

        for tier in ("low", "standard", "high"):
            file_path = variants[tier]
            assert os.path.exists(file_path)
            assert os.path.getsize(file_path) > 0

            # Probe each variant
            probe = await probe_media(file_path)
            streams = probe.get("streams", [])
            assert len(streams) == 1
            assert streams[0].get("codec_name") == "aac"
            assert streams[0].get("codec_type") == "audio"


@pytest.mark.asyncio
async def test_transcoder_video_conversion():
    """Unit test for FFmpeg transcoder with video input (extracts audio)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_video = os.path.join(tmpdir, "input.mp4")
        out_dir = os.path.join(tmpdir, "variants")
        generate_test_video(input_video, duration=2)

        variants, duration, source_type = await transcode_variants(input_video, out_dir)

        assert source_type == "video_conversion"
        assert 1.8 <= duration <= 2.2
        assert "low" in variants and "standard" in variants and "high" in variants

        for tier in ("low", "standard", "high"):
            file_path = variants[tier]
            assert os.path.exists(file_path)
            probe = await probe_media(file_path)
            streams = probe.get("streams", [])
            # Assert video stream stripped, only audio remains
            assert all(s.get("codec_type") != "video" for s in streams)
            assert any(s.get("codec_type") == "audio" for s in streams)


class MockMsg:
    def __init__(self, data: bytes, subject: str = "upload.received"):
        self.data = data
        self.subject = subject
        self.acked = False
        self.naked = False

    async def ack(self):
        self.acked = True

    async def nak(self, delay: float = 0):
        self.naked = True


@pytest.mark.asyncio
async def test_process_message_direct():
    """
    Direct unit/integration test for process_message execution:
    1. Uploads a 2s WAV file to MinIO blipp-raw-uploads.
    2. Persists upload in uploads table.
    3. Executes process_message with a MockMsg.
    4. Verifies MockMsg was acked.
    5. Verifies:
       - 3 variants exist in MinIO blipp-audio-variants bucket.
       - upload status is 'done'.
       - blipp record is created with duration ~ 2.0s and status 'published'.
       - transcode.complete is published on JetStream.
    """
    await init_db()
    pool = await get_db_pool()

    test_user_id = uuid.uuid4()
    test_username = f"creator_{test_user_id.hex[:8]}"

    # Ensure user profile exists
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
            """,
            test_user_id,
            test_username,
            "Transcode Test User",
        )

    nc = await nats.connect(servers=[settings.NATS_URL])
    js = nc.jetstream()
    await ensure_streams(js)

    complete_sub = await js.subscribe(
        subject="transcode.complete",
        deliver_policy=DeliverPolicy.NEW,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        test_audio_path = os.path.join(tmpdir, "sample.wav")
        generate_test_audio(test_audio_path, duration=2)

        upload_id = uuid.uuid4()
        raw_storage_key = f"raw/{upload_id}/sample.wav"
        raw_file_url = await storage_manager.upload_file(
            file_path=test_audio_path,
            storage_key=raw_storage_key,
            bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
            content_type="audio/wav",
        )

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO uploads (
                    upload_id, creator_id, raw_file_url, upload_type,
                    processing_status, title, description
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                upload_id,
                test_user_id,
                raw_file_url,
                "audio",
                "queued",
                "Direct Process Message Track",
                "Synthetic track test",
            )

        event_payload = {
            "upload_id": str(upload_id),
            "creator_id": str(test_user_id),
            "raw_file_url": raw_file_url,
            "upload_type": "audio",
            "title": "Direct Process Message Track",
            "description": "Synthetic track test",
        }

        mock_msg = MockMsg(data=json.dumps(event_payload).encode("utf-8"))
        await process_message(js, mock_msg)
        assert mock_msg.acked is True
        assert mock_msg.naked is False

        # Verify transcode.complete event received on JetStream
        comp_msg = await complete_sub.next_msg(timeout=10.0)
        await comp_msg.ack()
        comp_data = json.loads(comp_msg.data.decode("utf-8"))

        assert comp_data.get("upload_id") == str(upload_id)
        assert "blipp_id" in comp_data
        new_blipp_id = uuid.UUID(comp_data["blipp_id"])
        variants = comp_data.get("variants", {})
        assert "low" in variants and "standard" in variants and "high" in variants
        assert 1.8 <= comp_data.get("duration_seconds", 0.0) <= 2.2

        # Verify database upload is done
        upload_rec = await get_upload(upload_id)
        assert upload_rec is not None
        assert upload_rec["processing_status"] == "done"

        # Verify blipp row
        async with pool.acquire() as conn:
            blipp_row = await conn.fetchrow(
                """
                SELECT blipp_id, creator_id, title, description, audio_url,
                       audio_variants, duration_seconds, language, status,
                       source_type, parent_upload_id
                FROM blipps
                WHERE blipp_id = $1
                """,
                new_blipp_id,
            )

        assert blipp_row is not None
        assert blipp_row["creator_id"] == test_user_id
        assert blipp_row["parent_upload_id"] == upload_id
        assert blipp_row["status"] == "published"
        assert blipp_row["source_type"] == "direct_upload"
        assert 1.8 <= blipp_row["duration_seconds"] <= 2.2

        row_variants = blipp_row["audio_variants"]
        if isinstance(row_variants, str):
            row_variants = json.loads(row_variants)
        assert "low" in row_variants and "standard" in row_variants and "high" in row_variants

        # Verify 3 variants in MinIO
        for tier in ("low", "standard", "high"):
            tier_storage_key = f"{upload_id}/{tier}.m4a"
            tier_download_path = os.path.join(tmpdir, f"verified_{tier}.m4a")
            await storage_manager.download_file(
                storage_key=tier_storage_key,
                dest_path=tier_download_path,
                bucket_name=settings.S3_BUCKET_AUDIO_VARIANTS,
            )
            assert os.path.exists(tier_download_path)
            assert os.path.getsize(tier_download_path) > 0

    await complete_sub.drain()
    await nc.drain()
    await nc.close()
    await close_db()


@pytest.mark.asyncio
async def test_live_worker_pipeline():
    """
    End-to-end integration test verifying the live running worker service
    consumes upload.received from JetStream, processes the job, and publishes transcode.complete.
    """
    await init_db()
    pool = await get_db_pool()

    test_user_id = uuid.uuid4()
    test_username = f"creator_{test_user_id.hex[:8]}"

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users_profile (user_id, username, display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
            """,
            test_user_id,
            test_username,
            "Live Pipeline User",
        )

    nc = await nats.connect(servers=[settings.NATS_URL])
    js = nc.jetstream()
    await ensure_streams(js)

    complete_sub = await js.subscribe(
        subject="transcode.complete",
        deliver_policy=DeliverPolicy.NEW,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        test_audio_path = os.path.join(tmpdir, "live_sample.wav")
        generate_test_audio(test_audio_path, duration=2)

        upload_id = uuid.uuid4()
        raw_storage_key = f"raw/{upload_id}/live_sample.wav"
        raw_file_url = await storage_manager.upload_file(
            file_path=test_audio_path,
            storage_key=raw_storage_key,
            bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
            content_type="audio/wav",
        )

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO uploads (
                    upload_id, creator_id, raw_file_url, upload_type,
                    processing_status, title, description
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                upload_id,
                test_user_id,
                raw_file_url,
                "audio",
                "queued",
                "Live Worker Pipeline Track",
                "Synthetic track test",
            )

        event_payload = {
            "upload_id": str(upload_id),
            "creator_id": str(test_user_id),
            "raw_file_url": raw_file_url,
            "upload_type": "audio",
            "title": "Live Worker Pipeline Track",
            "description": "Synthetic track test",
        }

        # Publish upload.received to JetStream - live worker will consume and process
        await js.publish(
            subject="upload.received",
            payload=json.dumps(event_payload).encode("utf-8"),
        )

        # Await transcode.complete emitted by the live worker
        comp_msg = await complete_sub.next_msg(timeout=20.0)
        await comp_msg.ack()
        comp_data = json.loads(comp_msg.data.decode("utf-8"))

        assert comp_data.get("upload_id") == str(upload_id)
        assert "blipp_id" in comp_data
        new_blipp_id = uuid.UUID(comp_data["blipp_id"])
        variants = comp_data.get("variants", {})
        assert "low" in variants and "standard" in variants and "high" in variants

        # Verify DB upload is done
        upload_rec = await get_upload(upload_id)
        assert upload_rec is not None
        assert upload_rec["processing_status"] == "done"

        # Verify blipp row
        async with pool.acquire() as conn:
            blipp_row = await conn.fetchrow(
                """
                SELECT blipp_id, creator_id, title, duration_seconds, status, parent_upload_id
                FROM blipps
                WHERE blipp_id = $1
                """,
                new_blipp_id,
            )
        assert blipp_row is not None
        assert blipp_row["status"] == "published"
        assert blipp_row["parent_upload_id"] == upload_id
        assert 1.8 <= blipp_row["duration_seconds"] <= 2.2

    await complete_sub.drain()
    await nc.drain()
    await nc.close()
    await close_db()

