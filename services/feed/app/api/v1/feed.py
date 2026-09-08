import os
import json
import uuid
import logging
import mimetypes
from typing import Optional, List
import httpx
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import FileResponse

from blipp_common.config import settings
from blipp_common.security import get_optional_current_user, AuthenticatedUser
from blipp_common.database import get_db_pool
from blipp_common.storage import storage_service
from blipp_common.exceptions import AppException
from app.core.redis import get_redis_client
from app.models.schemas import FeedResponse, FeedItemResponse

logger = logging.getLogger("feed-service.api.feed")

router = APIRouter(tags=["Audio Reels Feed"])


@router.get("", response_model=FeedResponse)
@router.get("/", response_model=FeedResponse)
async def get_feed(
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_current_user),
):
    """
    Section 6.4: Multi-stage ranked feed orchestration:
    - Stage 1 (Cache): Query Redis for pre-computed candidate array tied to user.
    - Stage 2 (RecSys Fetch): On cache miss, query Gorse REST API for recommendations & cache in Redis with 5-minute TTL.
    - Stage 3 (Hydration): Query PostgreSQL to resolve candidate IDs into media entities, preserving exact ranking order.
    - Stage 4 (Cold-Start Injection): Query PostgreSQL for recent blipps with < 50 listens, interleaving into feed response.
    """
    user_id_str = str(current_user.user_id) if current_user else "anonymous"
    cache_key = f"feed:{user_id_str}"
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
            gorse_url = f"{settings.GORSE_API_URL.rstrip('/')}/api/recommend/{user_id_str}?n=20"
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

            # Cache in Redis with 5-minute (300s) TTL
            if candidate_ids:
                try:
                    redis_client = await get_redis_client()
                    await redis_client.set(cache_key, json.dumps(candidate_ids), ex=300)
                except Exception as cache_err:
                    logger.warning(f"Failed to cache candidate IDs in Redis: {cache_err}")

        except Exception as e:
            logger.warning(f"Gorse recommendation fetch error: {e}")

    pool = await get_db_pool()
    if not pool:
        return FeedResponse(items=[], next_cursor=None)

    # ─── Stage 3: Database Hydration with Strict Ranking ────────────────────
    hydrated_rows = []
    seen_blipp_ids = set()

    # Parse candidate IDs to valid UUIDs
    valid_candidate_uuids = []
    for cid in candidate_ids:
        try:
            valid_candidate_uuids.append(uuid.UUID(str(cid)))
        except (ValueError, TypeError):
            continue

    try:
        async with pool.acquire() as conn:
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
                        u.username,
                        COALESCE(u.display_name, u.username, 'Creator') AS display_name,
                        u.avatar_url
                    FROM blipps b
                    LEFT JOIN users_profile u ON b.creator_id = u.user_id
                    WHERE b.blipp_id = ANY($1::uuid[]) AND b.status = 'published'
                    ORDER BY array_position($1::uuid[], b.blipp_id);
                    """,
                    valid_candidate_uuids,
                )
                hydrated_rows = list(rows)
                seen_blipp_ids = {r["blipp_id"] for r in hydrated_rows}

            # If Gorse had no recommendations or fewer than 20 items,
            # supplement with latest published blipps:
            if len(hydrated_rows) < 20:
                needed = 20 - len(hydrated_rows)
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
                        u.username,
                        COALESCE(u.display_name, u.username, 'Creator') AS display_name,
                        u.avatar_url
                    FROM blipps b
                    LEFT JOIN users_profile u ON b.creator_id = u.user_id
                    WHERE b.status = 'published'
                      AND NOT (b.blipp_id = ANY($1::uuid[]))
                    ORDER BY b.created_at DESC
                    LIMIT $2;
                    """,
                    list(seen_blipp_ids),
                    needed,
                )
                for fr in fallback_rows:
                    hydrated_rows.append(fr)
                    seen_blipp_ids.add(fr["blipp_id"])

            # ─── Stage 4: Cold-Start Exploration Injection ──────────────────
            # Retrieve up to 2 recent published blipps that have < 50 total listens
            cold_start_rows = await conn.fetch(
                """
                SELECT 
                    b.blipp_id, 
                    b.creator_id, 
                    b.title, 
                    b.description, 
                    b.audio_url, 
                    b.audio_variants, 
                    b.duration_seconds, 
                    u.username, 
                    COALESCE(u.display_name, u.username, 'Creator') AS display_name, 
                    u.avatar_url
                FROM blipps b
                LEFT JOIN users_profile u ON b.creator_id = u.user_id
                WHERE b.status = 'published'
                  AND NOT (b.blipp_id = ANY($1::uuid[]))
                  AND (
                      SELECT COUNT(*)
                      FROM listening_session_agg lsa
                      WHERE lsa.blipp_id = b.blipp_id
                  ) < 50
                ORDER BY b.created_at DESC
                LIMIT 2;
                """,
                list(seen_blipp_ids),
            )

    except Exception as e:
        logger.exception(f"Error hydrating feed from database: {e}")
        return FeedResponse(items=[], next_cursor=None)

    # Interleave cold-start items into the ranked feed (at index 1 and index 4)
    final_rows = list(hydrated_rows)
    cold_items = list(cold_start_rows)
    if cold_items:
        insert_idx_1 = min(1, len(final_rows))
        final_rows.insert(insert_idx_1, cold_items[0])
        if len(cold_items) > 1:
            insert_idx_2 = min(4, len(final_rows))
            final_rows.insert(insert_idx_2, cold_items[1])

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
