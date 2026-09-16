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
from blipp_common.pagination import (
    decode_cursor, encode_cursor,
    encode_ranked_cursor, decode_ranked_cursor, cursor_is_ranked,
)
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
    T2 FIX — Coherent ranked feed with correct pagination:

    Ordering model:
      1. Gorse candidate sequence (up to 200 items, fetched once, cached in Redis 300s)
      2. Ranked cursor (candidate position) slices through the Gorse list across pages
      3. Only AFTER the Gorse candidate pool is exhausted, fall back to chronological order
      4. Chronological fallback uses a separate (created_at, blipp_id) cursor

    Cursor types (encoded in cursor string prefix):
      r:<base64> — ranked cursor, position in the Redis-cached Gorse candidate list
      c:<base64> — chronological cursor, for post-Gorse fallback pages
    """
    user_id_str = str(current_user.user_id)
    # Session-stable cache key: the same candidate list is reused across pages
    # TTL is 300s (5 min) to survive a full multi-page scrolling session.
    cache_key = f"feed:candidates:{user_id_str}"
    candidate_ids: List[str] = []
    redis_client = None

    # ─── Stage 1: Redis Candidate Cache ─────────────────────────────────────
    try:
        redis_client = await get_redis_client()
        if redis_client is not None:
            cached_val = await redis_client.get(cache_key)
            if cached_val:
                candidate_ids = json.loads(cached_val)
                logger.debug(f"Redis cache HIT for {cache_key}: {len(candidate_ids)} candidates")
    except Exception as e:
        logger.warning(f"Redis cache read error for {cache_key}: {e}")

    # ─── Stage 2: Gorse Fetch on Cache Miss ─────────────────────────────────
    if not candidate_ids:
        try:
            # Fetch up to 200 candidates to support multi-page ranked sessions
            gorse_url = f"{settings.GORSE_API_URL.rstrip('/')}/api/recommend/{user_id_str}?n=200"
            headers: dict = {}
            if settings.GORSE_API_KEY:
                headers["X-API-Key"] = settings.GORSE_API_KEY

            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(gorse_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    candidate_ids = [str(item) for item in data] if isinstance(data, list) else []
                    logger.info(f"Fetched {len(candidate_ids)} Gorse candidates for user {user_id_str}")

                    if candidate_ids and redis_client is not None:
                        try:
                            # 300s TTL to survive full scrolling session across multiple pages
                            await redis_client.setex(cache_key, 300, json.dumps(candidate_ids))
                        except Exception as cache_err:
                            logger.warning(f"Failed to write Gorse candidates to Redis: {cache_err}")
        except Exception as e:
            logger.warning(f"Gorse recommendation fetch error for user {user_id_str}: {e}")

    # ─── Parse Cursor ────────────────────────────────────────────────────────
    ranked_cursor = decode_ranked_cursor(cursor)
    chron_cursor = decode_cursor(cursor) if not ranked_cursor else None

    if cursor and ranked_cursor is None and chron_cursor is None:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CURSOR",
            message="Cursor must be a valid feed cursor",
        )

    pool = await get_db_pool()
    if not pool:
        return FeedResponse(items=[], next_cursor=None, has_more=False)

    # ─── Stage 3: Determine page source ─────────────────────────────────────
    # If we have a ranked cursor, slice into the cached candidate list
    # If we have a chron cursor (or no cursor after candidate pool exhausted), use chronological
    hydrated_ranked_rows: List[dict] = []
    fallback_rows: List[dict] = []
    candidate_start_pos = 0
    using_ranked_source = False

    if candidate_ids and (ranked_cursor is not None or cursor is None):
        # Ranked path: slice candidates from cursor position or start
        if ranked_cursor is not None:
            candidate_start_pos, _cached_key = ranked_cursor
        else:
            candidate_start_pos = 0

        # Take (limit + 1) candidates from position for has_more detection
        page_candidates = candidate_ids[candidate_start_pos : candidate_start_pos + limit + 1]

        if page_candidates:
            valid_candidate_uuids: List[uuid.UUID] = []
            for cid in page_candidates:
                try:
                    valid_candidate_uuids.append(uuid.UUID(str(cid)))
                except (ValueError, TypeError):
                    continue

            try:
                async with pool.acquire() as conn:
                    cand_rows = await conn.fetch(
                        """
                        SELECT 
                            b.blipp_id, b.creator_id, b.title, b.description,
                            b.audio_url, b.audio_variants, b.duration_seconds,
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
                # Preserve exact Gorse rank ordering (not DB insertion order)
                for cid in valid_candidate_uuids:
                    if cid in cand_dict:
                        hydrated_ranked_rows.append(cand_dict[cid])
                using_ranked_source = True
            except Exception as e:
                logger.exception(f"Error hydrating Gorse candidates: {e}")

    # ─── Stage 4: Chronological Fallback ────────────────────────────────────
    # Used when: (a) no Gorse candidates, (b) candidate pool exhausted, (c) chron cursor active
    ranked_count = len(hydrated_ranked_rows)
    needed = (limit + 1) - ranked_count

    if needed > 0:
        # Only fall back to chronological when candidate pool is fully consumed
        # or when client explicitly holds a chron cursor from a previous fallback page
        already_seen_ids = [r["blipp_id"] for r in hydrated_ranked_rows]
        all_candidate_uuids: List[uuid.UUID] = []
        for cid in candidate_ids:
            try:
                all_candidate_uuids.append(uuid.UUID(str(cid)))
            except (ValueError, TypeError):
                continue

        # Exclude ALL known Gorse candidates (not just this page) to avoid duplicates
        exclude_ids = list(set(already_seen_ids + all_candidate_uuids))

        cursor_created_at = chron_cursor[0] if chron_cursor else None
        cursor_blipp_id = chron_cursor[1] if chron_cursor else None
        cursor_blipp_uuid = None
        if cursor_blipp_id:
            try:
                cursor_blipp_uuid = uuid.UUID(cursor_blipp_id)
            except (ValueError, TypeError):
                pass

        try:
            async with pool.acquire() as conn:
                if exclude_ids:
                    f_rows = await conn.fetch(
                        """
                        SELECT 
                            b.blipp_id, b.creator_id, b.title, b.description,
                            b.audio_url, b.audio_variants, b.duration_seconds,
                            b.created_at,
                            b.author_username as username,
                            b.author_display_name as display_name,
                            b.author_avatar_url as avatar_url
                        FROM feed_items b
                        WHERE NOT (b.blipp_id = ANY($1::uuid[]))
                          AND ($2::timestamptz IS NULL OR (b.created_at, b.blipp_id) < ($2, $3::uuid))
                        ORDER BY b.created_at DESC, b.blipp_id DESC
                        LIMIT $4
                        """,
                        exclude_ids,
                        cursor_created_at,
                        cursor_blipp_uuid,
                        needed,
                    )
                else:
                    f_rows = await conn.fetch(
                        """
                        SELECT 
                            b.blipp_id, b.creator_id, b.title, b.description,
                            b.audio_url, b.audio_variants, b.duration_seconds,
                            b.created_at,
                            b.author_username as username,
                            b.author_display_name as display_name,
                            b.author_avatar_url as avatar_url
                        FROM feed_items b
                        WHERE ($1::timestamptz IS NULL OR (b.created_at, b.blipp_id) < ($1, $2::uuid))
                        ORDER BY b.created_at DESC, b.blipp_id DESC
                        LIMIT $3
                        """,
                        cursor_created_at,
                        cursor_blipp_uuid,
                        needed,
                    )
            fallback_rows = [dict(r) for r in f_rows]
        except Exception as e:
            logger.exception(f"Error querying chronological fallback feed: {e}")

    # ─── Stage 5: Merge, deduplicate, build response page ───────────────────
    combined_rows = hydrated_ranked_rows + fallback_rows
    unique_rows: List[dict] = []
    seen_ids: set = set()
    for row in combined_rows:
        if row["blipp_id"] not in seen_ids:
            unique_rows.append(row)
            seen_ids.add(row["blipp_id"])

    has_more = len(unique_rows) > limit
    page_rows = unique_rows[:limit]

    if not page_rows:
        return FeedResponse(items=[], next_cursor=None, has_more=False)

    # ─── Stage 6: Enrich with Authoritative Engagement State ────────────────
    page_blipp_ids = [r["blipp_id"] for r in page_rows]
    page_creator_ids = [r["creator_id"] for r in page_rows if r.get("creator_id")]

    likes_count_map: Dict[uuid.UUID, int] = {}
    user_liked_set: set = set()
    user_saved_set: set = set()
    user_following_set: set = set()

    try:
        async with pool.acquire() as conn:
            stats_rows = await conn.fetch(
                "SELECT blipp_id, likes_count FROM feed_item_stats WHERE blipp_id = ANY($1::uuid[])",
                page_blipp_ids,
            )
            for sr in stats_rows:
                likes_count_map[sr["blipp_id"]] = sr["likes_count"]

            like_rows = await conn.fetch(
                "SELECT blipp_id FROM user_likes_projection WHERE user_id = $1 AND blipp_id = ANY($2::uuid[])",
                current_user.user_id,
                page_blipp_ids,
            )
            user_liked_set = {lr["blipp_id"] for lr in like_rows}

            save_rows = await conn.fetch(
                "SELECT blipp_id FROM user_saves_projection WHERE user_id = $1 AND blipp_id = ANY($2::uuid[])",
                current_user.user_id,
                page_blipp_ids,
            )
            user_saved_set = {sr["blipp_id"] for sr in save_rows}

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

    # ─── Stage 7: Emit next cursor (ranked or chronological) ─────────────────
    next_cursor: Optional[str] = None
    if has_more:
        if using_ranked_source and ranked_count >= limit:
            # We served a full ranked page — emit a ranked cursor for the next page
            next_position = candidate_start_pos + limit
            next_cursor = encode_ranked_cursor(next_position, cache_key)
        else:
            # We dipped into chronological fallback — emit a chron cursor
            last_row = page_rows[-1]
            next_cursor = encode_cursor(last_row["created_at"], str(last_row["blipp_id"]))

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
