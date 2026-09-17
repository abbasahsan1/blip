import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from blipp_common.config import settings
from blipp_common.database import get_db_pool
from blipp_common.events import event_bus
from blipp_common.exceptions import AppException
from blipp_common.outbox import record_outbox_event
from blipp_common.pagination import decode_cursor, encode_cursor
from blipp_common.security import AuthenticatedUser, get_current_user

logger = logging.getLogger("social-graph.api.saves")
router = APIRouter(tags=["Blipp Saves & Bookmarks"])


class SaveActionResponse(BaseModel):
    status: str
    blipp_id: uuid.UUID


class SavedBlippItem(BaseModel):
    blipp_id: uuid.UUID
    creator_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    description: Optional[str] = None
    audio_url: str = ""
    audio_variants: Dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    author: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    saved_at: datetime
    created_at: Optional[datetime] = None


class SavedBlippsResponse(BaseModel):
    items: List[SavedBlippItem] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool = False


@router.post("/blipps/{blipp_id}/save", response_model=SaveActionResponse, status_code=status.HTTP_200_OK)
@router.post("/saves/{blipp_id}", response_model=SaveActionResponse, status_code=status.HTTP_200_OK)
async def save_blipp(
    blipp_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Saves/bookmarks a Blipp for the authenticated user within Social Graph domain.
    Idempotent operation recording bookmark and emitting an engagement.save event atomically.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    now = datetime.now(timezone.utc)
    # T22: Do NOT pre-generate event_id — record_outbox_event() mints the canonical
    # event_id and injects it into the payload automatically.
    event_payload = {
        "event_type": "save",
        "user_id": str(current_user.user_id),
        "blipp_id": str(blipp_id),
        "occurred_at": now.isoformat(),
        "position_seconds": 0.0,
    }

    async with pool.acquire() as conn:
        async with conn.transaction():
            # T23: Use RETURNING to detect an actual insert vs. a conflict no-op.
            # Only emit an outbox event when the save is a new state transition
            # (absent → present). Repeated saves of the same blipp produce zero events.
            inserted = await conn.fetchrow(
                """
                INSERT INTO saves (user_id, blipp_id, created_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, blipp_id) DO NOTHING
                RETURNING blipp_id
                """,
                current_user.user_id,
                blipp_id,
                now,
            )
            if inserted is not None:
                # T21: Outbox is the ONLY publisher — no eager event_bus.publish().
                await record_outbox_event(conn, "engagement.save", event_payload)

    return SaveActionResponse(status="saved", blipp_id=blipp_id)


@router.delete("/blipps/{blipp_id}/save", response_model=SaveActionResponse, status_code=status.HTTP_200_OK)
@router.delete("/saves/{blipp_id}", response_model=SaveActionResponse, status_code=status.HTTP_200_OK)
async def unsave_blipp(
    blipp_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Removes a saved/bookmarked Blipp for the authenticated user within Social Graph domain.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    now = datetime.now(timezone.utc)
    # T22: No pre-generated event_id — record_outbox_event() injects the canonical one.
    event_payload = {
        "event_type": "unsave",
        "user_id": str(current_user.user_id),
        "blipp_id": str(blipp_id),
        "occurred_at": now.isoformat(),
        "position_seconds": 0.0,
    }

    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute(
                "DELETE FROM saves WHERE user_id = $1 AND blipp_id = $2",
                current_user.user_id,
                blipp_id,
            )
            if res == "DELETE 1":
                await record_outbox_event(conn, "engagement.unsave", event_payload)

    # T21: Outbox is the ONLY publisher — no eager event_bus.publish().
    logger.info(f"Removed saved blipp {blipp_id} for user {current_user.user_id}")
    return SaveActionResponse(status="unsaved", blipp_id=blipp_id)


@router.get("/blipps/saved", response_model=SavedBlippsResponse)
@router.get("/saves", response_model=SavedBlippsResponse)
async def get_saved_blipps(
    limit: int = Query(20, ge=1, le=100, description="Maximum items per page"),
    cursor: Optional[str] = Query(None, description="Cursor for backward pagination"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns cursor-paginated list of saved/bookmarked audio reels for the authenticated user.
    Fetches saved IDs from Social Graph and hydrates metadata from Feed Service without cross-db queries.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    fetch_limit = limit + 1
    cursor_dt: Optional[datetime] = None
    if cursor:
        decoded = decode_cursor(cursor)
        if decoded:
            cursor_dt, _ = decoded
        else:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except ValueError:
                raise AppException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="INVALID_CURSOR",
                    message="Cursor must be a valid cursor string",
                )

    async with pool.acquire() as conn:
        if cursor_dt:
            rows = await conn.fetch(
                """
                SELECT blipp_id, created_at AS saved_at
                FROM saves
                WHERE user_id = $1 AND created_at < $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                current_user.user_id,
                cursor_dt,
                fetch_limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT blipp_id, created_at AS saved_at
                FROM saves
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                current_user.user_id,
                fetch_limit,
            )

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    if not page_rows:
        return SavedBlippsResponse(items=[], next_cursor=None, has_more=False)

    saved_map = {str(r["blipp_id"]): r["saved_at"] for r in page_rows}
    blipp_ids = [str(r["blipp_id"]) for r in page_rows]

    # Hydrate metadata from Feed service
    feed_url = getattr(settings, "FEED_SERVICE_URL", "http://feed-service.blipp.svc.cluster.local:8002")
    hydrated_items: Dict[str, Dict[str, Any]] = {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                f"{feed_url.rstrip('/')}/v1/feed/items/batch",
                json={"blipp_ids": blipp_ids},
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    hydrated_items[str(item["blipp_id"])] = item
    except Exception as e:
        logger.warning(f"Could not hydrate saved blipps from feed-service at {feed_url}: {e}")

    items = []
    for bid_str in blipp_ids:
        bid = uuid.UUID(bid_str)
        saved_at = saved_map[bid_str]
        meta = hydrated_items.get(bid_str, {})
        creator_id_str = meta.get("creator_id")
        creator_id = uuid.UUID(creator_id_str) if creator_id_str else None

        items.append(
            SavedBlippItem(
                blipp_id=bid,
                creator_id=creator_id,
                title=meta.get("title") or "Saved Blipp",
                description=meta.get("description"),
                audio_url=meta.get("audio_url", ""),
                audio_variants=meta.get("audio_variants", {}),
                duration_seconds=float(meta.get("duration_seconds", 0.0)),
                author=meta.get("author") or meta.get("display_name"),
                username=meta.get("username"),
                display_name=meta.get("display_name"),
                avatar_url=meta.get("avatar_url"),
                saved_at=saved_at,
                created_at=meta.get("created_at"),
            )
        )

    next_cursor = None
    if has_more and page_rows:
        last_item = page_rows[-1]
        next_cursor = encode_cursor(last_item["saved_at"], last_item["blipp_id"])

    return SavedBlippsResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
