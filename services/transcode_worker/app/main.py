import os
import json
import uuid
import signal
import asyncio
import logging
import tempfile
from typing import Optional

import nats
from nats.aio.client import Client as NATSClient
from nats.js.client import JetStreamContext
from nats.js.api import StreamConfig, StorageType, RetentionPolicy

from app.config import settings
from blipp_common.storage import storage_manager
from app.transcoder import transcode_variants
from app.database import (
    init_db,
    close_db,
    update_upload_status,
    get_upload,
    create_blipp,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("transcode-worker")

_running = True


def handle_shutdown(sig, frame):
    global _running
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    _running = False


async def ensure_streams(js: JetStreamContext) -> None:
    """
    Ensures that stream UPLOADS exists and includes both upload.> and transcode.>
    """
    stream_name = settings.NATS_STREAM_UPLOADS
    subjects = ["upload.>", "transcode.>"]
    try:
        await js.stream_info(stream_name)
        try:
            await js.update_stream(name=stream_name, subjects=subjects)
            logger.info(f"Updated stream '{stream_name}' subjects to {subjects}")
        except Exception:
            pass
    except Exception:
        try:
            await js.add_stream(
                name=stream_name,
                subjects=subjects,
                storage=StorageType.FILE,
                retention=RetentionPolicy.LIMITS,
            )
            logger.info(f"Created stream '{stream_name}' with subjects {subjects}")
        except Exception as e:
            logger.warning(f"Could not create stream '{stream_name}': {e}")


async def process_message(js: JetStreamContext, msg) -> None:
    raw_data = msg.data.decode("utf-8")
    logger.info(f"Processing message on subject '{msg.subject}': {raw_data}")
    try:
        data = json.loads(raw_data)
    except Exception as e:
        logger.error(f"Malformed JSON in job: {e}")
        await msg.ack()
        return

    upload_id_str = data.get("upload_id")
    if not upload_id_str:
        logger.warning(f"Missing upload_id in job: {raw_data}")
        await msg.ack()
        return

    upload_id = uuid.UUID(upload_id_str)
    creator_id_str = data.get("creator_id")
    creator_id = uuid.UUID(creator_id_str) if creator_id_str else None
    raw_file_url = data.get("raw_file_url")
    title = data.get("title")
    description = data.get("description")

    with tempfile.TemporaryDirectory(prefix=f"transcode_{upload_id}_") as tmpdir:
        input_filename = os.path.basename(storage_manager.extract_storage_key(raw_file_url)) or "input.bin"
        local_input_path = os.path.join(tmpdir, input_filename)

        try:
            # 1. Update status to transcoding
            await update_upload_status(upload_id, "transcoding")

            # 2. Download source file from blipp-raw-uploads bucket
            storage_key = storage_manager.extract_storage_key(raw_file_url)
            logger.info(f"Downloading raw source '{storage_key}' from {storage_manager.raw_bucket}...")
            await storage_manager.download_file(storage_key, local_input_path)

            # 3. Transcode into 3 audio tiers and measure exact duration
            output_dir = os.path.join(tmpdir, "output")
            logger.info(f"Transcoding '{local_input_path}' into 3 tiers (low, standard, high)...")
            variants_local, duration_seconds, detected_source_type = await transcode_variants(
                local_input_path, output_dir
            )

            # 4. Upload the 3 variants to blipp-audio-variants bucket in MinIO
            uploaded_variants = {}
            for tier in ("low", "standard", "high"):
                tier_file = variants_local[tier]
                variant_key = f"{upload_id}/{tier}.m4a"
                variant_url = await storage_manager.upload_file(
                    file_path=tier_file,
                    storage_key=variant_key,
                    content_type="audio/mp4",
                )
                uploaded_variants[tier] = variant_url
                logger.info(f"Uploaded {tier} variant to {variant_url}")

            canonical_audio_url = uploaded_variants["high"]

            # Hydrate creator_id / metadata if not fully populated in the event payload
            if not creator_id:
                upload_rec = await get_upload(upload_id)
                if upload_rec:
                    creator_id = upload_rec["creator_id"]
                    title = title or upload_rec.get("title")
                    description = description or upload_rec.get("description")

            if not creator_id:
                raise RuntimeError(f"Creator ID could not be determined for upload {upload_id}")

            # 5. Insert Blipp record into PostgreSQL
            # TODO: temporary status='published' until automated copyright scanner is active (Section 6.2)
            new_blipp_id = uuid.uuid4()
            await create_blipp(
                blipp_id=new_blipp_id,
                creator_id=creator_id,
                title=title or "Untitled Blipp",
                description=description,
                audio_url=canonical_audio_url,
                audio_variants=uploaded_variants,
                duration_seconds=duration_seconds,
                source_type=detected_source_type,
                parent_upload_id=upload_id,
                status="published",
            )
            logger.info(f"Created Blipp {new_blipp_id} (duration={duration_seconds:.2f}s, status=published)")

            # 6. Update source Upload record: processing_status = 'done'
            await update_upload_status(upload_id, "done")

            # 7. Publish transcode.complete event to NATS JetStream
            complete_payload = {
                "blipp_id": str(new_blipp_id),
                "upload_id": str(upload_id),
                "variants": uploaded_variants,
                "duration_seconds": float(duration_seconds),
            }
            await js.publish(
                subject="transcode.complete",
                payload=json.dumps(complete_payload).encode("utf-8"),
            )
            logger.info(f"Published transcode.complete for upload {upload_id}")

            # 8. Acknowledge (ack) message
            await msg.ack()
            logger.info(f"Successfully finished job for upload {upload_id}")

        except Exception as e:
            logger.exception(f"Error during transcoding of upload {upload_id}: {e}")
            try:
                await update_upload_status(upload_id, "failed")
            except Exception as db_err:
                logger.error(f"Failed to update upload status to failed: {db_err}")

            delivery_count = getattr(getattr(msg, "metadata", None), "num_delivered", 1)
            if delivery_count >= 3:
                logger.warning(f"Upload {upload_id} exceeded max retries ({delivery_count}); acknowledging.")
                try:
                    await msg.ack()
                except Exception:
                    pass
            else:
                try:
                    await msg.nak(delay=5)
                except Exception as nak_err:
                    logger.error(f"Failed to nak message: {nak_err}")


async def run_worker() -> None:
    global _running

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("Initializing database pool...")
    await init_db()

    logger.info(f"Connecting to NATS at {settings.NATS_URL}...")
    nc: NATSClient = await nats.connect(
        servers=[settings.NATS_URL],
        name="transcode-worker",
        reconnect_time_wait=2,
        max_reconnect_attempts=60,
    )
    js = nc.jetstream()

    await ensure_streams(js)

    logger.info(f"Binding durable consumer '{settings.NATS_CONSUMER_GROUP}' on subject 'upload.received'...")
    psub = await js.pull_subscribe(
        subject="upload.received",
        durable=settings.NATS_CONSUMER_GROUP,
        stream=settings.NATS_STREAM_UPLOADS,
    )

    logger.info("Transcode Worker ready and waiting for jobs...")

    while _running:
        try:
            msgs = await psub.fetch(batch=1, timeout=2.0)
            for msg in msgs:
                await process_message(js, msg)
        except (nats.errors.TimeoutError, asyncio.TimeoutError):
            continue
        except Exception as e:
            if _running:
                logger.warning(f"Error in pull fetch loop: {e}")
                await asyncio.sleep(1.0)

    logger.info("Worker shutting down, closing connections...")
    try:
        await psub.unsubscribe()
        await nc.drain()
        await nc.close()
    except Exception as e:
        logger.warning(f"Error during NATS close: {e}")
    await close_db()
    logger.info("Worker shutdown complete.")


def main():
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
