import os
import json
import uuid
import logging
import mimetypes
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, status, HTTPException
from fastapi.responses import FileResponse

from app.core.security import get_current_user
from app.core.database import get_db_pool
from app.core.storage import storage_service
from app.core.exceptions import AppException
from app.models.schemas import TokenData, BlippResponse, FeedResponse, FeedItemResponse

logger = logging.getLogger("auth-service.api.blipps")

router = APIRouter(prefix="/blipps", tags=["Audio Reels & Blipps"])


@router.post("/upload", response_model=BlippResponse, status_code=status.HTTP_201_CREATED)
async def upload_blipp(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    duration_seconds: int = Form(0),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Direct Audio Ingestion endpoint:
    1. Requires valid user JWT (get_current_user).
    2. Uploads audio file to S3/R2 or local storage using creator_id prefix.
    3. Persists record into the PostgreSQL blipps table.
    4. Returns created Blipp object.
    """
    if not file or not file.filename:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_FILE",
            message="An audio file must be uploaded",
        )

    # Save to storage with creator_id prefix
    try:
        audio_url = storage_service.save_file(
            file_obj=file.file,
            original_filename=file.filename,
            content_type=file.content_type,
            creator_id=str(current_user.user_id),
        )
    except Exception as e:
        logger.exception(f"Storage upload error: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="STORAGE_ERROR",
            message="Failed to store uploaded audio file",
        )

    audio_variants = {"standard": audio_url}
    new_blipp_id = uuid.uuid4()
    pool = await get_db_pool()

    if not pool:
        logger.error("Database pool unavailable")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database service is currently unavailable",
        )

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO blipps (
                    blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                RETURNING blipp_id, creator_id, title, audio_url, audio_variants, duration_seconds, status, created_at
                """,
                new_blipp_id,
                current_user.user_id,
                title,
                audio_url,
                json.dumps(audio_variants),
                max(0, duration_seconds),
                "published",
            )
    except Exception as e:
        logger.exception(f"Database insertion error: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to save blipp record",
        )

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
async def get_feed():
    """
    Returns a simple chronological list of published blipps with hydrated author profiles.
    """
    pool = await get_db_pool()
    if not pool:
        # Graceful fallback if database is restarting
        return FeedResponse(items=[], next_cursor=None)

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    b.blipp_id, 
                    b.creator_id, 
                    b.title, 
                    b.audio_url, 
                    b.audio_variants, 
                    b.duration_seconds,
                    u.username,
                    COALESCE(u.display_name, u.username, 'Creator') AS display_name,
                    u.avatar_url
                FROM blipps b
                LEFT JOIN users_profile u ON b.creator_id = u.user_id
                WHERE b.status = 'published'
                ORDER BY b.created_at DESC
                LIMIT 50
                """
            )
    except Exception as e:
        logger.exception(f"Error fetching blipp feed: {e}")
        return FeedResponse(items=[], next_cursor=None)

    items = []
    for r in rows:
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

    return FeedResponse(items=items, next_cursor=None)


@router.api_route("/audio/{filename:path}", methods=["GET", "HEAD"])
async def stream_audio(filename: str):
    """
    Public audio stream endpoint with HTTP Range / Partial Content support for local storage fallback.
    """
    local_path = storage_service.get_local_path(filename)
    if not local_path:
        raise HTTPException(status_code=404, detail="Audio file not found")

    mime_type, _ = mimetypes.guess_type(str(local_path))
    if not mime_type or not mime_type.startswith("audio"):
        mime_type = "audio/mpeg"

    return FileResponse(
        path=local_path,
        media_type=mime_type,
        filename=os.path.basename(filename) if "os" in globals() else filename.split("/")[-1],
    )
