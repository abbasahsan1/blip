import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from blipp_common.config import settings
from blipp_common.database import get_db_pool
from blipp_common.events import event_bus
from blipp_common.exceptions import AppException
from blipp_common.security import TokenData, get_current_user
from blipp_common.storage import storage_service
from app.models.schemas import UploadResponse, UploadStatusResponse

logger = logging.getLogger("content-ingest.api.uploads")
router = APIRouter(tags=["Content Ingest & Uploads"])


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
    """The sole upload path: stream multipart audio to MinIO and queue transcode."""
    if upload_type == "smart_clip":
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Smart clip uploads are not implemented")

    upload_id = uuid.uuid4()
    extension = os.path.splitext(file.filename or "")[1].lower() or ".mp3"
    storage_key = f"{current_user.user_id}/{upload_id}{extension}"
    content_type = file.content_type or storage_service.normalize_mime_type(file.filename or storage_key)
    pool = await get_db_pool()
    if not pool:
        raise AppException(status_code=500, code="DATABASE_UNAVAILABLE", message="Database pool unavailable")

    raw_file_url = await storage_service.upload_stream(
        file=file,
        storage_key=storage_key,
        bucket_name=settings.S3_BUCKET_RAW_UPLOADS,
        content_type=content_type,
    )
    now = datetime.now(timezone.utc)
    upload_payload = {
        "upload_id": str(upload_id),
        "creator_id": str(current_user.user_id),
        "raw_file_url": raw_file_url,
        "upload_type": upload_type,
        "title": title or "",
        "description": description or "",
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "author_username": current_user.username or "",
        "author_display_name": current_user.first_name or current_user.username or "",
        "author_avatar_url": getattr(current_user, "avatar_url", None),
        "timestamp": now.isoformat(),
    }

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO uploads (upload_id, creator_id, raw_file_url, upload_type, processing_status, title, description, created_at)
                    VALUES ($1, $2, $3, $4, 'created', $5, $6, $7)
                    """,
                    upload_id, current_user.user_id, raw_file_url, upload_type, title, description, now,
                )
                from blipp_common.outbox import record_outbox_event
                await record_outbox_event(conn, "upload.received", upload_payload)
    except Exception as exc:
        logger.exception("Could not persist upload %s", upload_id)
        raise AppException(status_code=500, code="DATABASE_ERROR", message="Failed to persist upload record") from exc

    try:
        await event_bus.publish("upload.received", upload_payload)
    except Exception as exc:
        logger.warning("Eager publish of upload.received for %s delayed (outbox will deliver): %s", upload_id, exc)

    return UploadResponse(upload_id=upload_id, status="queued", message="Upload received and queued for processing")


@router.get("/{upload_id}", response_model=UploadStatusResponse)
async def get_upload_status(upload_id: uuid.UUID, current_user: TokenData = Depends(get_current_user)):
    pool = await get_db_pool()
    if not pool:
        raise AppException(status_code=500, code="DATABASE_UNAVAILABLE", message="Database pool unavailable")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT upload_id, creator_id, raw_file_url, upload_type, processing_status, title, description, created_at
            FROM uploads WHERE upload_id = $1
            """, upload_id,
        )
    if not row:
        raise AppException(status_code=404, code="NOT_FOUND", message=f"Upload '{upload_id}' not found")
    if row["creator_id"] != current_user.user_id:
        raise AppException(status_code=403, code="FORBIDDEN", message="You do not have permission to view this upload")
    return UploadStatusResponse(
        upload_id=row["upload_id"], creator_id=row["creator_id"], raw_file_url=row["raw_file_url"],
        upload_type=row["upload_type"], processing_status=row["processing_status"], title=row["title"],
        description=row["description"], created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )
