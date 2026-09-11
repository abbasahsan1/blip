import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Request, status, HTTPException, File, Form, UploadFile

from blipp_common.config import settings
from blipp_common.security import get_current_user, AuthenticatedUser, TokenData
from blipp_common.database import get_db_pool
from blipp_common.storage import storage_service
from blipp_common.events import event_bus
from blipp_common.exceptions import AppException
from app.models.schemas import (
    UploadResponse,
    UploadStatusResponse,
    UploadPresignRequest,
    UploadPresignResponse,
    UploadCompleteRequest,
    BlippResponse,
)

logger = logging.getLogger("content-ingest.api.uploads")

router = APIRouter(tags=["Content Ingest & Uploads"])

# In-memory session registry for staged uploads
_pending_uploads: Dict[str, Dict[str, Any]] = {}


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
@router.post("/", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_media(
    file: UploadFile = File(...),
    upload_type: str = Form("audio"),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    scheduled_at: Optional[datetime] = Form(None),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Asynchronous Upload Pipeline (Section 5.3):
    Streams file chunks directly to MinIO raw uploads bucket, records the upload in Postgres,
    and publishes an upload.received event to NATS JetStream.
    """
    if upload_type == "smart_clip":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Smart clip uploads are not implemented"
        )

    upload_id = uuid.uuid4()
    ext = os.path.splitext(file.filename or "")[1].lower() or ".mp3"
    storage_key = f"{current_user.user_id}/{upload_id}{ext}"
    content_type = file.content_type or storage_service.normalize_mime_type(file.filename or storage_key)

    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    # 1. Stream file chunks asynchronously into blipp-raw-uploads MinIO bucket
    raw_file_url = await storage_service.upload_stream(
        file=file,
        storage_key=storage_key,
        bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
        content_type=content_type,
    )

    # 2. Ensure creator profile exists and commit Upload record to Postgres
    now_utc = datetime.now(timezone.utc)
    try:
        async with pool.acquire() as conn:
            # Guarantee user profile row exists for foreign key constraint
            existing = await conn.fetchval(
                "SELECT user_id FROM users_profile WHERE user_id = $1",
                current_user.user_id,
            )
            if not existing:
                uname = current_user.username or str(current_user.user_id)
                taken = await conn.fetchval(
                    "SELECT user_id FROM users_profile WHERE username = $1",
                    uname,
                )
                if taken:
                    uname = f"{uname}_{str(current_user.user_id)[:8]}"
                await conn.execute(
                    """
                    INSERT INTO users_profile (user_id, username, display_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    current_user.user_id,
                    uname,
                    current_user.first_name or uname or "Creator",
                )
            await conn.execute(
                """
                INSERT INTO uploads (
                    upload_id, creator_id, raw_file_url, upload_type, processing_status, title, description, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                upload_id,
                current_user.user_id,
                raw_file_url,
                upload_type,
                "queued",
                title,
                description,
                now_utc,
            )
    except Exception as e:
        logger.exception(f"Error persisting upload record: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to persist upload record",
        )

    # 3. Publish upload.received message to NATS JetStream (UPLOADS stream)
    nats_payload = {
        "upload_id": str(upload_id),
        "creator_id": str(current_user.user_id),
        "raw_file_url": raw_file_url,
        "upload_type": upload_type,
        "title": title or "",
        "description": description or "",
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "timestamp": now_utc.isoformat(),
    }
    try:
        await event_bus.publish(subject="upload.received", payload=nats_payload)
    except Exception as e:
        logger.warning(f"Failed to publish upload.received event: {e}")

    # 4. Return HTTP 202 Accepted
    return UploadResponse(
        upload_id=upload_id,
        status="queued",
        message="Upload received and queued for processing",
    )


@router.get("/{upload_id}", response_model=UploadStatusResponse, status_code=status.HTTP_200_OK)
async def get_upload_status(
    upload_id: uuid.UUID,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Retrieve upload status and metadata for creators to track their processing pipeline.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT upload_id, creator_id, raw_file_url, upload_type, processing_status, title, description, created_at
            FROM uploads
            WHERE upload_id = $1
            """,
            upload_id,
        )

    if not row:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message=f"Upload '{upload_id}' not found",
        )

    if row["creator_id"] != current_user.user_id:
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="You do not have permission to view this upload",
        )

    return UploadStatusResponse(
        upload_id=row["upload_id"],
        creator_id=row["creator_id"],
        raw_file_url=row["raw_file_url"],
        upload_type=row["upload_type"],
        processing_status=row["processing_status"],
        title=row["title"],
        description=row["description"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )


@router.post("/presign", response_model=UploadPresignResponse, status_code=status.HTTP_200_OK)
async def presign_upload(
    req: UploadPresignRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Stage 1: Presign upload ticket and issue direct PUT URL.
    """
    upload_id = str(uuid.uuid4())
    ext = os.path.splitext(req.file_name)[1].lower() or ".mp3"
    storage_key = f"{current_user.user_id}/{upload_id}{ext}"
    content_type = storage_service.normalize_mime_type(req.file_name, req.mime_type)

    _pending_uploads[upload_id] = {
        "storage_key": storage_key,
        "creator_id": current_user.user_id,
        "file_name": req.file_name,
        "mime_type": content_type,
        "size_bytes": req.size_bytes,
    }

    if storage_service.use_s3 and storage_service.s3_client and storage_service.bucket_name:
        try:
            presigned_url = storage_service.s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": storage_service.bucket_name,
                    "Key": storage_key,
                    "ContentType": content_type,
                },
                ExpiresIn=3600,
            )
            return UploadPresignResponse(
                upload_id=upload_id,
                storage_key=storage_key,
                presigned_url=presigned_url,
                content_type=content_type,
            )
        except Exception as e:
            logger.warning(f"Failed to generate S3 presigned URL: {e}. Falling back to direct cluster upload.")

    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    presigned_url = f"{base_url}/v1/uploads/direct/{storage_key}"

    return UploadPresignResponse(
        upload_id=upload_id,
        storage_key=storage_key,
        presigned_url=presigned_url,
        content_type=content_type,
    )


@router.put("/direct/{storage_key:path}", status_code=status.HTTP_200_OK)
async def direct_binary_upload(storage_key: str, request: Request):
    """
    Stage 2: Receive raw binary stream and write to disk for local storage mode.
    """
    safe_key = storage_key.lstrip("/")
    local_path = storage_service.local_dir / safe_key
    local_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(local_path, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
        return {"status": "ok", "storage_key": safe_key}
    except Exception as e:
        logger.exception(f"Error saving direct binary upload: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="UPLOAD_WRITE_ERROR",
            message="Failed to write uploaded binary stream",
        )


@router.post("/{upload_id}/complete", response_model=BlippResponse, status_code=status.HTTP_201_CREATED)
async def complete_upload(
    upload_id: str,
    req: UploadCompleteRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Stage 3: Complete ingest, create blipp record in PostgreSQL, and publish.
    """
    upload_info = _pending_uploads.get(upload_id)
    default_key = f"{current_user.user_id}/{upload_id}.mp3"
    storage_key = upload_info.get("storage_key") if upload_info else default_key

    audio_url = storage_service.sanitize_public_url(storage_service.get_playback_url(storage_key))
    audio_variants = {"standard": audio_url}
    new_blipp_id = uuid.uuid4()
    pool = await get_db_pool()

    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    now_utc = datetime.now(timezone.utc)
    if settings.FEATURE_COPYRIGHT_SCAN_ENABLED:
        computed_status = "processing"
    elif req.scheduled_at and req.scheduled_at > now_utc:
        computed_status = "scheduled"
    else:
        computed_status = "published"

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO blipps (
                    blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status, scheduled_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status, scheduled_at, created_at
                """,
                new_blipp_id,
                current_user.user_id,
                req.title,
                audio_url,
                json.dumps(audio_variants),
                max(0, req.duration_seconds),
                computed_status,
                req.scheduled_at,
            )
    except Exception as e:
        logger.exception(f"Error persisting completed upload: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to persist blipp record",
        )

    _pending_uploads.pop(upload_id, None)

    if computed_status == "published":
        try:
            await event_bus.publish(
                subject="engagement.blipp.published",
                payload={
                    "blipp_id": str(new_blipp_id),
                    "creator_id": str(current_user.user_id),
                    "title": req.title,
                    "audio_url": audio_url,
                    "duration_seconds": max(0, req.duration_seconds),
                    "published_at": now_utc.isoformat(),
                },
            )
        except Exception as pub_err:
            logger.warning(f"Failed to publish engagement.blipp.published event: {pub_err}")
    elif computed_status == "processing":
        try:
            await event_bus.publish(
                subject="copyright.scan.requested",
                payload={
                    "blipp_id": str(new_blipp_id),
                    "upload_id": upload_id,
                    "audio_url": audio_url,
                },
            )
        except Exception as scan_err:
            logger.warning(f"Failed to publish copyright.scan.requested event: {scan_err}")

    created_at_str = row["created_at"].isoformat() if row["created_at"] else None
    raw_variants = row["audio_variants"]
    parsed_variants = json.loads(raw_variants) if isinstance(raw_variants, str) else (raw_variants or audio_variants)

    return BlippResponse(
        blipp_id=row["blipp_id"],
        creator_id=row["creator_id"],
        title=row["title"],
        audio_url=row["audio_url"],
        audio_variants=parsed_variants,
        duration_seconds=row["duration_seconds"],
        status=row["status"],
        created_at=created_at_str,
    )


from pydantic import BaseModel

class UploadStatusUpdateRequest(BaseModel):
    status: str

@router.patch("/{upload_id}/status", response_model=BlippResponse, status_code=status.HTTP_200_OK)
async def update_upload_status(
    upload_id: uuid.UUID,
    req: UploadStatusUpdateRequest,
):
    """
    Internal endpoint to update the blipp status (e.g. to 'published' after copyright clearance).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    now_utc = datetime.now(timezone.utc)
    
    async with pool.acquire() as conn:
        # Check if the blipp exists using parent_upload_id
        row = await conn.fetchrow(
            """
            UPDATE blipps
            SET status = $1
            WHERE parent_upload_id = $2
            RETURNING blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status, created_at
            """,
            req.status,
            upload_id
        )

        if not row:
            # Fallback if parent_upload_id wasn't set but it matches blipp_id
            row = await conn.fetchrow(
                """
                UPDATE blipps
                SET status = $1
                WHERE blipp_id = $2
                RETURNING blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status, created_at
                """,
                req.status,
                upload_id
            )

        if not row:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="NOT_FOUND",
                message=f"Blipp for upload/id '{upload_id}' not found",
            )
            
        if req.status == "published":
            await conn.execute(
                """
                UPDATE uploads
                SET processing_status = 'done'
                WHERE upload_id = $1
                """,
                upload_id
            )
            
    if req.status == "published":
        try:
            await event_bus.publish(
                subject="engagement.blipp.published",
                payload={
                    "blipp_id": str(row["blipp_id"]),
                    "creator_id": str(row["creator_id"]),
                    "title": row["title"] or "",
                    "audio_url": row["audio_url"],
                    "duration_seconds": float(row["duration_seconds"] or 0.0),
                    "published_at": now_utc.isoformat(),
                },
            )
            logger.info(f"Published engagement.blipp.published event for blipp {row['blipp_id']}")
        except Exception as pub_err:
            logger.warning(f"Failed to publish engagement.blipp.published event: {pub_err}")

    created_at_str = row["created_at"].isoformat() if row["created_at"] else None
    raw_variants = row["audio_variants"]
    parsed_variants = json.loads(raw_variants) if isinstance(raw_variants, str) else (raw_variants or {"standard": row["audio_url"]})

    return BlippResponse(
        blipp_id=row["blipp_id"],
        creator_id=row["creator_id"],
        title=row["title"],
        audio_url=row["audio_url"],
        audio_variants=parsed_variants,
        duration_seconds=row["duration_seconds"],
        status=row["status"],
        created_at=created_at_str,
    )
