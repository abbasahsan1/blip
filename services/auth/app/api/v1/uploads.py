import os
import uuid
import json
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Request, status, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security import get_current_user
from app.core.database import get_db_pool
from app.core.storage import storage_service
from app.core.exceptions import AppException
from app.models.schemas import (
    TokenData,
    UploadPresignRequest,
    UploadPresignResponse,
    UploadCompleteRequest,
    BlippResponse,
    FeedResponse,
    FeedItemResponse,
    TelemetryEvent,
)

logger = logging.getLogger("auth-service.api.uploads")

router = APIRouter(tags=["Multi-stage Uploads & Feed"])

# In-memory session registry for staged uploads
_pending_uploads: Dict[str, Dict[str, Any]] = {}


@router.post("/uploads/presign", response_model=UploadPresignResponse, status_code=status.HTTP_200_OK)
async def presign_upload(
    req: UploadPresignRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Stage 1: Presign upload ticket and issue direct PUT URL.
    Supports real direct S3/B2 presigned URLs, with fallback to local direct stream endpoint.
    Storage key is scoped to creator_id.
    """
    upload_id = str(uuid.uuid4())
    ext = os.path.splitext(req.file_name)[1].lower() or ".mp3"
    storage_key = f"{current_user.user_id}/{upload_id}{ext}"
    content_type = storage_service.normalize_mime_type(req.file_name, req.mime_type)

    # Store staging metadata
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

    # Local fallback direct upload endpoint
    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    presigned_url = f"{base_url}/v1/uploads/direct/{storage_key}"

    return UploadPresignResponse(
        upload_id=upload_id,
        storage_key=storage_key,
        presigned_url=presigned_url,
        content_type=content_type,
    )


@router.put("/uploads/direct/{storage_key:path}", status_code=status.HTTP_200_OK)
async def direct_binary_upload(storage_key: str, request: Request):
    """
    Stage 2: Receive raw binary stream and write to disk for local storage mode.
    Handles subpaths such as {creator_id}/{upload_id}.mp3.
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


@router.post("/uploads/{upload_id}/complete", response_model=BlippResponse, status_code=status.HTTP_201_CREATED)
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

    audio_url = storage_service.get_playback_url(storage_key)
    audio_variants = {"standard": audio_url}
    new_blipp_id = uuid.uuid4()
    pool = await get_db_pool()

    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO blipps (
                    blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status, created_at
                """,
                new_blipp_id,
                current_user.user_id,
                req.title,
                audio_url,
                json.dumps(audio_variants),
                max(0, req.duration_seconds),
                "published",
            )
    except Exception as e:
        logger.exception(f"Error persisting completed upload: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to persist blipp record",
        )

    # Clean up staging info
    _pending_uploads.pop(upload_id, None)

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


@router.get("/feed", response_model=FeedResponse)
async def get_feed(cursor: Optional[str] = None, limit: int = 10):
    """
    Paginated chronological feed endpoint supporting cursor pagination and user profile hydration.
    """
    pool = await get_db_pool()
    if not pool:
        return FeedResponse(items=[], next_cursor=None)

    limit = min(max(1, limit), 50)

    try:
        async with pool.acquire() as conn:
            if cursor:
                rows = await conn.fetch(
                    """
                    SELECT 
                        b.blipp_id, 
                        b.creator_id, 
                        b.title, 
                        b.audio_url, 
                        b.audio_variants, 
                        b.duration_seconds, 
                        b.created_at,
                        u.username,
                        COALESCE(u.display_name, u.username, 'Creator') AS display_name,
                        u.avatar_url
                    FROM blipps b
                    LEFT JOIN users_profile u ON b.creator_id = u.user_id
                    WHERE b.status = 'published' AND b.created_at < $1::timestamptz
                    ORDER BY b.created_at DESC
                    LIMIT $2
                    """,
                    cursor,
                    limit + 1,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT 
                        b.blipp_id, 
                        b.creator_id, 
                        b.title, 
                        b.audio_url, 
                        b.audio_variants, 
                        b.duration_seconds, 
                        b.created_at,
                        u.username,
                        COALESCE(u.display_name, u.username, 'Creator') AS display_name,
                        u.avatar_url
                    FROM blipps b
                    LEFT JOIN users_profile u ON b.creator_id = u.user_id
                    WHERE b.status = 'published'
                    ORDER BY b.created_at DESC
                    LIMIT $1
                    """,
                    limit + 1,
                )
    except Exception as e:
        logger.exception(f"Error fetching feed: {e}")
        return FeedResponse(items=[], next_cursor=None)

    has_more = len(rows) > limit
    selected_rows = rows[:limit]
    next_cursor = selected_rows[-1]["created_at"].isoformat() if has_more and selected_rows else None

    items = []
    for r in selected_rows:
        raw_variants = r["audio_variants"]
        parsed_variants = json.loads(raw_variants) if isinstance(raw_variants, str) else (raw_variants or {})
        playback_url = storage_service.get_playback_url(r["audio_url"])
        if not parsed_variants and playback_url:
            parsed_variants = {"standard": playback_url}
        elif "standard" in parsed_variants:
            parsed_variants["standard"] = storage_service.get_playback_url(parsed_variants["standard"])

        items.append(
            FeedItemResponse(
                blipp_id=r["blipp_id"],
                creator_id=r["creator_id"],
                title=r["title"],
                audio_url=playback_url,
                audio_variants=parsed_variants,
                duration_seconds=r["duration_seconds"],
                author=r["display_name"],
                username=r["username"],
                display_name=r["display_name"],
                avatar_url=r["avatar_url"],
            )
        )

    return FeedResponse(items=items, next_cursor=next_cursor)

