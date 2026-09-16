import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Query, status

from blipp_common.config import settings
from blipp_common.database import get_db_pool
from blipp_common.exceptions import AppException
from blipp_common.pagination import decode_cursor, encode_cursor
from blipp_common.redis import get_redis_client
from blipp_common.security import AuthenticatedUser, get_current_user
from blipp_common.storage import storage_service
from app.models.schemas import (
    BatchFeedItemsRequest,
    BatchFeedItemsResponse,
    FeedItemResponse,
    FeedResponse,
)

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
    Multi-stage ranked feed orchestration:
    - Stage 1 (Cache): Query Redis for pre-computed candidate array tied to user.
    - Stage 2 (RecSys Fetch): Query Gorse REST API for recommendations & cache.
    - Stage 3 (Hydration & Ranking Preservation): Hydrate candidate entities strictly preserving Gorse rank order.
    - Stage 4 (Cold Start / Fill): Fill remaining slots with recent chronological blipps.
    - Stage 5 (Authoritative Engagement): Enrich each item with server-authoritative like, save, and follow state.
    """
    user_id_str = str(current_user.user_id)
    cache_key = f"feed:user:{user_id_str}"
    candidate_ids: List[str] = []

    # ─── Stage 1: Redis Candidate Cache ─────────────────────────────────────
    try:
        redis_client = await get_redis_client()
        if redis_client is not None:
            cached_val = await redis_client.get(cache_key)
            if cached_val:
                candidate_ids = json.loads(cached_val)
                logger.debug(f"Redis cache HIT for {cache_key}: {len(candidate_ids)} items")
    except Exception as e:
        logger.warning(f"Redis cache read error for {cache_key}: {e}")

    # ─── Stage 2: RecSys Fetch (Gorse) on Cache Miss ────────────────────────
    if not candidate_ids:
        try:
            gorse_url = f"{settings.GORSE_API_URL.rstrip('/')}/api/recommend/{user_id_str}?n=40"
            headers = {}
            if settings.GORSE_API_KEY:
                headers["X-API-Key"] = settings.GORSE_API_KEY

            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(gorse_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    candidate_ids = [str(item) for item in data] if isinstance(data, list) else []
                    logger.info(f"Fetched {len(candidate_ids)} ranked recommendations from Gorse")

                    if candidate_ids and redis_client is not None:
                        try:
                            await redis_client.setex(cache_key, 60, json.dumps(candidate_ids))
                        except Exception as cache_err:
                            logger.warning(f"Failed to write Gorse recommendations to Redis: {cache_err}")
        except Exception as e:
            logger.warning(f"Gorse recommendation fetch error: {e}")

    # Parse cursor if provided
    decoded_cursor = decode_cursor(cursor)
    if cursor and not decoded_cursor:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CURSOR",
            message="Cursor must be a valid feed cursor",
        )

    cursor_created_at, cursor_blipp_id = decoded_cursor or (None, None)
    cursor_blipp_uuid = None
    if cursor_blipp_id:
        try:
            cursor_blipp_uuid = uuid.UUID(cursor_blipp_id)
        except (ValueError, TypeError):
            pass

    pool = await get_db_pool()
    if not pool:
        return FeedResponse(items=[], next_cursor=None, has_more=False)

    valid_candidate_uuids: List[uuid.UUID] = []
    for cid in candidate_ids:
        try:
            valid_candidate_uuids.append(uuid.UUID(str(cid)))
        except (ValueError, TypeError):
            continue

    hydrated_ranked_rows: List[dict] = []
    fallback_rows: List[dict] = []

    try:
        async with pool.acquire() as conn:
            # ─── Stage 3: Hydration preserving Gorse candidate ordering ─────────
            # Only use candidate IDs on first page or when cursor is not active
            if valid_candidate_uuids and not cursor:
                cand_rows = await conn.fetch(
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
                    """,
                    valid_candidate_uuids,
                )
                cand_dict = {r["blipp_id"]: dict(r) for r in cand_rows}
                # Preserve exact Gorse rank ordering
                for cid in valid_candidate_uuids:
                    if cid in cand_dict:
                        hydrated_ranked_rows.append(cand_dict[cid])

            # ─── Stage 4: Cold-start or pagination fallback ────────────────────
            # Fill remaining items from chronological feed
            already_seen_ids = [r["blipp_id"] for r in hydrated_ranked_rows]
            needed = (limit + 1) - len(hydrated_ranked_rows)

            if needed > 0:
                if already_seen_ids:
                    f_rows = await conn.fetch(
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
                        already_seen_ids,
                        cursor_created_at,
                        cursor_blipp_uuid,
                        needed,
                    )
                else:
                    f_rows = await conn.fetch(
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
                        needed,
                    )
                fallback_rows = [dict(r) for r in f_rows]

    except Exception as e:
        logger.exception(f"Error querying feed items from database: {e}")
        return FeedResponse(items=[], next_cursor=None, has_more=False)

    combined_rows = hydrated_ranked_rows + fallback_rows
    # Deduplicate while strictly maintaining order
    unique_rows = []
    seen_ids = set()
    for row in combined_rows:
        if row["blipp_id"] not in seen_ids:
            unique_rows.append(row)
            seen_ids.add(row["blipp_id"])

    has_more = len(unique_rows) > limit
    page_rows = unique_rows[:limit]

    if not page_rows:
        return FeedResponse(items=[], next_cursor=None, has_more=False)

    # ─── Stage 5: Enrich with Authoritative Engagement State ────────────────
    page_blipp_ids = [r["blipp_id"] for r in page_rows]
    page_creator_ids = [r["creator_id"] for r in page_rows if r.get("creator_id")]

    likes_count_map: Dict[uuid.UUID, int] = {}
    user_liked_set = set()
    user_saved_set = set()
    user_following_set = set()

    try:
        async with pool.acquire() as conn:
            # Likes count from feed_item_stats
            stats_rows = await conn.fetch(
                "SELECT blipp_id, likes_count FROM feed_item_stats WHERE blipp_id = ANY($1::uuid[])",
                page_blipp_ids,
            )
            for sr in stats_rows:
                likes_count_map[sr["blipp_id"]] = sr["likes_count"]

            # User like state
            like_rows = await conn.fetch(
                "SELECT blipp_id FROM user_likes_projection WHERE user_id = $1 AND blipp_id = ANY($2::uuid[])",
                current_user.user_id,
                page_blipp_ids,
            )
            user_liked_set = {lr["blipp_id"] for lr in like_rows}

            # User save state
            save_rows = await conn.fetch(
                "SELECT blipp_id FROM user_saves_projection WHERE user_id = $1 AND blipp_id = ANY($2::uuid[])",
                current_user.user_id,
                page_blipp_ids,
            )
            user_saved_set = {sr["blipp_id"] for sr in save_rows}

            # User following state
            if page_creator_ids:
                follow_rows = await conn.fetch(
                    "SELECT followee_id FROM user_follows_projection WHERE follower_id = $1 AND followee_id = ANY($2::uuid[])",
                    current_user.user_id,
                    page_creator_ids,
                )
                user_following_set = {fr["followee_id"] for fr in follow_rows}
    except Exception as eng_err:
        logger.warning(f"Error enriching engagement state for feed: {eng_err}")

    # Build response items
    items: List[FeedItemResponse] = []
    for r in page_rows:
        raw_variants = r.get("audio_variants")
        parsed_variants = json.loads(raw_variants) if isinstance(raw_variants, str) else (raw_variants or {})
        playback_url = storage_service.sanitize_public_url(storage_service.get_playback_url(r["audio_url"]))
        if not parsed_variants and playback_url:
            parsed_variants = {"standard": playback_url}
        else:
            for k, v in list(parsed_variants.items()):
                parsed_variants[k] = storage_service.sanitize_public_url(storage_service.get_playback_url(v))

        bid = r["blipp_id"]
        cid = r.get("creator_id")
        items.append(
            FeedItemResponse(
                item_type="blipp",
                id=str(bid),
                blipp_id=bid,
                creator_id=cid,
                title=r.get("title") or "Untitled Broadcast",
                description=r.get("description"),
                audio_url=playback_url,
                audio_variants=parsed_variants,
                duration_seconds=float(r.get("duration_seconds") or 0.0),
                author=r.get("display_name") or r.get("username"),
                username=r.get("username"),
                display_name=r.get("display_name"),
                avatar_url=r.get("avatar_url"),
                creator={
                    "username": r.get("username"),
                    "display_name": r.get("display_name"),
                    "avatar_url": r.get("avatar_url"),
                } if r.get("username") else None,
                likes_count=likes_count_map.get(bid, 0),
                is_liked=(bid in user_liked_set),
                is_saved=(bid in user_saved_set),
                is_following=(cid in user_following_set if cid else False),
            )
        )

    next_cursor = (
        encode_cursor(page_rows[-1]["created_at"], str(page_rows[-1]["blipp_id"]))
        if has_more and page_rows
        else None
    )

    return FeedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/items/batch", response_model=BatchFeedItemsResponse)
@router.post("/feed/items/batch", response_model=BatchFeedItemsResponse)
async def get_feed_items_batch(
    req: BatchFeedItemsRequest,
):
    """
    Batch metadata hydration endpoint for internal microservice consumption.
    Allows other services (e.g. Social Graph Saved Blipps) to hydrate items
    without crossing database boundaries.
    """
    if not req.blipp_ids:
        return BatchFeedItemsResponse(items=[])

    valid_uuids = []
    for bid in req.blipp_ids:
        try:
            valid_uuids.append(uuid.UUID(str(bid)))
        except (ValueError, TypeError):
            continue

    if not valid_uuids:
        return BatchFeedItemsResponse(items=[])

    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    async with pool.acquire() as conn:
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
            """,
            valid_uuids,
        )

    items = []
    for r in rows:
        raw_variants = r.get("audio_variants")
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
                title=r.get("title") or "Untitled",
                description=r.get("description"),
                audio_url=playback_url,
                audio_variants=parsed_variants,
                duration_seconds=float(r.get("duration_seconds") or 0.0),
                author=r.get("display_name") or r.get("username"),
                username=r.get("username"),
                display_name=r.get("display_name"),
                avatar_url=r.get("avatar_url"),
                creator={
                    "username": r.get("username"),
                    "display_name": r.get("display_name"),
                    "avatar_url": r.get("avatar_url"),
                } if r.get("username") else None,
            )
        )

    return BatchFeedItemsResponse(items=items)
