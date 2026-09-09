import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from blipp_common.config import settings
from blipp_common.database import get_db_pool
from blipp_common.exceptions import AppException
from blipp_common.security import AuthenticatedUser, get_current_user, get_optional_current_user
from blipp_common.storage import storage_service
from app.models.messaging import StoryListResponse, StoryResponse

logger = logging.getLogger("messaging.api.stories")
router = APIRouter(prefix="/stories", tags=["24-Hour Ephemeral Audio Stories"])

STORIES_BUCKET = getattr(settings, "S3_BUCKET_STORIES", "blipp-stories") or "blipp-stories"


def _ensure_stories_bucket():
    """Ensure MinIO/S3 bucket for stories exists."""
    client = storage_service.internal_s3_client or storage_service.s3_client
    if storage_service.use_s3 and client:
        try:
            client.head_bucket(Bucket=STORIES_BUCKET)
        except Exception:
            try:
                client.create_bucket(Bucket=STORIES_BUCKET)
                logger.info(f"Created MinIO bucket '{STORIES_BUCKET}'")
            except Exception as e:
                logger.warning(f"Bucket '{STORIES_BUCKET}' existence check/creation note: {e}")


@router.post("", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
async def post_story(
    file: UploadFile = File(..., description="Audio file payload for 24h ephemeral story"),
    duration_seconds: float = Form(0.0, description="Audio track duration in seconds"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Posts an ephemeral audio story (§5.4).
    Accepts uploaded audio, streams to MinIO bucket blipp-stories,
    and sets expires_at = NOW() + INTERVAL '24 hours'.
    """
    _ensure_stories_bucket()

    story_id = uuid.uuid4()
    ext = os.path.splitext(file.filename or "")[1].lower() or ".mp3"
    storage_key = f"stories/{current_user.user_id}/{story_id}{ext}"
    content_type = file.content_type or storage_service.normalize_mime_type(file.filename or storage_key)

    # Stream audio file into blipp-stories bucket
    await storage_service.upload_stream(
        file=file,
        storage_key=storage_key,
        bucket_name=STORIES_BUCKET,
        content_type=content_type,
    )

    playback_url = storage_service.get_playback_url(storage_key, bucket_name=STORIES_BUCKET)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)

    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stories (story_id, creator_id, audio_url, duration_seconds, expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            story_id,
            current_user.user_id,
            playback_url,
            duration_seconds,
            expires_at,
            now,
        )

    logger.info(f"Published 24h audio story {story_id} for creator {current_user.user_id}, expires at {expires_at}")

    return StoryResponse(
        story_id=story_id,
        creator_id=current_user.user_id,
        audio_url=playback_url,
        duration_seconds=duration_seconds,
        expires_at=expires_at,
        created_at=now,
    )


@router.get("", response_model=StoryListResponse)
@router.get("/", response_model=StoryListResponse)
async def get_stories(
    include_self: bool = Query(True, description="Include authenticated user's own active stories"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Queries active audio stories from followed creators where expires_at > NOW() (§5.4).
    Resolves followed creators via the Social Graph Service.
    """
    target_creator_ids = []
    if include_self:
        target_creator_ids.append(current_user.user_id)

    # Fetch followed creator IDs from social-graph-service
    social_url = getattr(settings, "SOCIAL_GRAPH_URL", "http://social-graph-service.blipp.svc.cluster.local:8003")
    try:
        url = f"{social_url.rstrip('/')}/v1/social/{current_user.user_id}/following"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    try:
                        target_creator_ids.append(uuid.UUID(item["user_id"]))
                    except (ValueError, KeyError):
                        pass
    except Exception as e:
        logger.warning(f"Could not reach social-graph-service at {social_url}: {e}")

    # Fallback to checking local/shared follows table if available
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    # De-duplicate IDs
    unique_creator_ids = list({uid for uid in target_creator_ids})

    async with pool.acquire() as conn:
        # If no follows were retrieved from social graph service, try reading from follows table if it exists in db
        if len(unique_creator_ids) <= (1 if include_self else 0):
            try:
                follow_rows = await conn.fetch(
                    "SELECT followee_id FROM follows WHERE follower_id = $1",
                    current_user.user_id,
                )
                for fr in follow_rows:
                    unique_creator_ids.append(fr["followee_id"])
                unique_creator_ids = list({uid for uid in unique_creator_ids})
            except Exception:
                pass

        if not unique_creator_ids:
            return StoryListResponse(items=[], total=0)

        rows = await conn.fetch(
            """
            SELECT story_id, creator_id, audio_url, duration_seconds, expires_at, created_at
            FROM stories
            WHERE creator_id = ANY($1::uuid[]) AND expires_at > NOW()
            ORDER BY created_at DESC
            """,
            unique_creator_ids,
        )

        items = [
            StoryResponse(
                story_id=r["story_id"],
                creator_id=r["creator_id"],
                audio_url=r["audio_url"],
                duration_seconds=r["duration_seconds"],
                expires_at=r["expires_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

        return StoryListResponse(items=items, total=len(items))


@router.get("/{creator_id}", response_model=StoryListResponse)
async def get_creator_stories(
    creator_id: uuid.UUID,
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_current_user),
):
    """
    Queries active stories for a specific creator where expires_at > NOW() (§5.4).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT story_id, creator_id, audio_url, duration_seconds, expires_at, created_at
            FROM stories
            WHERE creator_id = $1 AND expires_at > NOW()
            ORDER BY created_at DESC
            """,
            creator_id,
        )

        items = [
            StoryResponse(
                story_id=r["story_id"],
                creator_id=r["creator_id"],
                audio_url=r["audio_url"],
                duration_seconds=r["duration_seconds"],
                expires_at=r["expires_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

        return StoryListResponse(items=items, total=len(items))
