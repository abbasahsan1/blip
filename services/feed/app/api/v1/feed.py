import os
import json
import uuid
import logging
import mimetypes
from typing import Optional, List
import httpx
from fastapi import APIRouter, Depends, Query, status, HTTPException
from fastapi.responses import FileResponse

from blipp_common.config import settings
from blipp_common.security import get_current_user, AuthenticatedUser
from blipp_common.database import get_db_pool
from blipp_common.storage import storage_service
from blipp_common.exceptions import AppException
from blipp_common.pagination import decode_cursor, encode_cursor
from blipp_common.redis import get_redis_client
from app.models.schemas import FeedResponse, FeedItemResponse

logger = logging.getLogger("feed-service.api.feed")

router = APIRouter(tags=["Audio Reels Feed"])


@router.get("", response_model=FeedResponse)
@router.get("/", response_model=FeedResponse)
async def get_feed(
    cursor: Optional[str] = Query(None, description="Cursor for feed pagination"),
    limit: int = Query(10, ge=1, le=20),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Section 6.4: Multi-stage ranked feed orchestration:
    - Stage 1 (Cache): Query Redis for pre-computed candidate array tied to user.
    - Stage 2 (RecSys Fetch): On cache miss, query Gorse REST API for recommendations & cache in Redis with 60s TTL.
    - Stage 3 (Hydration): Query PostgreSQL to resolve candidate IDs into media entities.
    - Stage 4 (Cold Start): Fill missing recommendations with recent published blipps.
    """
    user_id_str = str(current_user.user_id)
    cache_key = f"feed:user:{user_id_str}"
    candidate_ids: List[str] = []

    # ─── Stage 1: Redis Candidate Cache ─────────────────────────────────────
    try:
        redis_client = await get_redis_client()
        cached_val = await redis_client.get(cache_key)
        if cached_val:
            candidate_ids = json.loads(cached_val)
            logger.debug(f"Redis cache HIT for {cache_key}: {len(candidate_ids)} items")
    except Exception as e:
        logger.warning(f"Redis cache read error for {cache_key}: {e}")

    # ─── Stage 2: RecSys Fetch (Gorse) on Cache Miss ────────────────────────
    if not candidate_ids:
        try:
            gorse_url = f"{settings.GORSE_API_URL.rstrip('/')}/api/recommend/{user_id_str}?n=30"
            headers = {}
            if settings.GORSE_API_KEY:
                headers["X-API-Key"] = settings.GORSE_API_KEY

            async with httpx.AsyncClient(timeout=3.0) as http_client:
                resp = await http_client.get(gorse_url, headers=headers)
                if resp.status_code == 200:
                    raw_items = resp.json()
                    if isinstance(raw_items, list):
                        for item in raw_items:
                            if isinstance(item, str) and item:
                                candidate_ids.append(item)
                            elif isinstance(item, dict) and item.get("Id"):
                                candidate_ids.append(item["Id"])
                        logger.debug(f"Fetched {len(candidate_ids)} recommendations from Gorse for {user_id_str}")

            # Cache in Redis with 60-second TTL
            if candidate_ids:
                try:
                    redis_client = await get_redis_client()
                    await redis_client.set(cache_key, json.dumps(candidate_ids), ex=60)
                except Exception as cache_err:
                    logger.warning(f"Failed to cache candidate IDs in Redis: {cache_err}")

        except Exception as e:
            logger.warning(f"Gorse recommendation fetch error: {e}")

    decoded_cursor = decode_cursor(cursor)
    if cursor and not decoded_cursor:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CURSOR",
            message="Cursor must be a valid feed cursor",
        )

    cursor_created_at, cursor_blipp_id = decoded_cursor or (None, None)
    try:
        cursor_blipp_uuid = uuid.UUID(cursor_blipp_id) if cursor_blipp_id else None
    except (ValueError, TypeError):
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CURSOR",
            message="Cursor contains an invalid blipp ID",
        )

    pool = await get_db_pool()
    if not pool:
        return FeedResponse(items=[], next_cursor=None)

    # ─── Stage 3: Database hydration and cold-start fallback ────────────────
    # Fetch one extra row so `has_more` and `next_cursor` describe a real,
    # stable `(created_at, blipp_id)` page boundary.  Recommendation IDs are
    # preferred, but all rows retain this ordering to make pagination safe.
    hydrated_rows = []

    # Parse candidate IDs to valid UUIDs
    valid_candidate_uuids = []
    for cid in candidate_ids:
        try:
            valid_candidate_uuids.append(uuid.UUID(str(cid)))
        except (ValueError, TypeError):
            continue

    try:
        async with pool.acquire() as conn:
            fetch_limit = limit + 1
            if valid_candidate_uuids:
                rows = await conn.fetch(
                    """
                    SELECT 
                        b.blipp_id, 
                        b.creator_id, 
                        b.title, 
                        b.description,
                        b.audio_url, 
                        b.audio_variants, 
                        b.duration_seconds,
                        b.created_at,
                        b.author_username as username,
                        b.author_display_name as display_name,
                        b.author_avatar_url as avatar_url
                    FROM feed_items b
                    WHERE b.blipp_id = ANY($1::uuid[])
                      AND ($2::timestamptz IS NULL OR (b.created_at, b.blipp_id) < ($2, $3::uuid))
                    ORDER BY b.created_at DESC, b.blipp_id DESC
                    LIMIT $4;
                    """,
                    valid_candidate_uuids,
                    cursor_created_at,
                    cursor_blipp_uuid,
                    fetch_limit,
                )
                hydrated_rows = list(rows)

            if hydrated_rows:
                fallback_rows = await conn.fetch(
                    """
                        SELECT 
                            b.blipp_id, 
                            b.creator_id, 
                            b.title, 
                            b.description,
                            b.audio_url, 
                            b.audio_variants, 
                            b.duration_seconds,
                            b.created_at,
                            b.author_username as username,
                            b.author_display_name as display_name,
                            b.author_avatar_url as avatar_url
                        FROM feed_items b
                        WHERE NOT (b.blipp_id = ANY($1::uuid[]))
                          AND ($2::timestamptz IS NULL OR (b.created_at, b.blipp_id) < ($2, $3::uuid))
                        ORDER BY b.created_at DESC, b.blipp_id DESC
                        LIMIT $4;
                    """,
                    [r["blipp_id"] for r in hydrated_rows],
                    cursor_created_at,
                    cursor_blipp_uuid,
                    fetch_limit,
                )
            else:
                fallback_rows = await conn.fetch(
                    """
                        SELECT 
                            b.blipp_id, 
                            b.creator_id, 
                            b.title, 
                            b.description,
                            b.audio_url, 
                            b.audio_variants, 
                            b.duration_seconds,
                            b.created_at,
                            b.author_username as username,
                            b.author_display_name as display_name,
                            b.author_avatar_url as avatar_url
                        FROM feed_items b
                        WHERE ($1::timestamptz IS NULL OR (b.created_at, b.blipp_id) < ($1, $2::uuid))
                        ORDER BY b.created_at DESC, b.blipp_id DESC
                        LIMIT $3;
                    """,
                    cursor_created_at,
                    cursor_blipp_uuid,
                    fetch_limit,
                )
            hydrated_rows.extend(fallback_rows)

    except Exception as e:
        logger.exception(f"Error hydrating feed from database: {e}")
        return FeedResponse(items=[], next_cursor=None, has_more=False)

    # Keep the cursor ordering consistent even when recommended and fallback
    # records are combined. Deduplicate before choosing the page.
    ordered_rows = sorted(hydrated_rows, key=lambda row: (row["created_at"], row["blipp_id"]), reverse=True)
    unique_rows = []
    seen_blipp_ids = set()
    for row in ordered_rows:
        if row["blipp_id"] not in seen_blipp_ids:
            unique_rows.append(row)
            seen_blipp_ids.add(row["blipp_id"])
    has_more = len(unique_rows) > limit
    final_rows = unique_rows[:limit]

    # Transform to FeedItemResponse with presigned playback URLs
    items = []
    for r in final_rows:
        raw_variants = r["audio_variants"]
        parsed_variants = json.loads(raw_variants) if isinstance(raw_variants, str) else (raw_variants or {})
        playback_url = storage_service.sanitize_public_url(storage_service.get_playback_url(r["audio_url"]))
        if not parsed_variants and playback_url:
            parsed_variants = {"standard": playback_url}
        else:
            for k, v in list(parsed_variants.items()):
                parsed_variants[k] = storage_service.sanitize_public_url(storage_service.get_playback_url(v))

        items.append(
            FeedItemResponse(
                item_type="blipp",
                id=str(r["blipp_id"]),
                blipp_id=r["blipp_id"],
                creator_id=r["creator_id"],
                title=r["title"],
                description=r["description"],
                audio_url=playback_url,
                audio_variants=parsed_variants,
                duration_seconds=r["duration_seconds"],
                author=r["display_name"],
                username=r["username"],
                display_name=r["display_name"],
                avatar_url=r["avatar_url"],
                creator={
                    "username": r["username"],
                    "display_name": r["display_name"],
                    "avatar_url": r["avatar_url"],
                } if r.get("username") else None,
            )
        )

    final_feed_items = items

    next_cursor = (
        encode_cursor(final_rows[-1]["created_at"], str(final_rows[-1]["blipp_id"]))
        if has_more and final_rows
        else None
    )

    return FeedResponse(items=final_feed_items, next_cursor=next_cursor, has_more=has_more)


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
