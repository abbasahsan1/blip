import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from blipp_common.database import get_db_pool
from blipp_common.events import event_bus
from blipp_common.exceptions import AppException
from blipp_common.pagination import decode_cursor, encode_cursor
from blipp_common.security import AuthenticatedUser, get_current_user
from app.models.schemas import SaveActionResponse, SavedBlippItem, SavedBlippsResponse

logger = logging.getLogger("content-ingest.api.saves")
router = APIRouter(tags=["Blipp Saves & Bookmarks"])


@router.get("/blipps/saved", response_model=SavedBlippsResponse)
async def get_saved_blipps(
    limit: int = Query(20, ge=1, le=100, description="Maximum items per page"),
    cursor: Optional[str] = Query(None, description="Cursor for backward pagination"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns cursor-paginated list of audio reels saved/bookmarked by the authenticated user (§5.3).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    fetch_limit = limit + 1
    async with pool.acquire() as conn:
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
                    b.language,
                    b.status,
                    s.created_at AS saved_at,
                    b.created_at AS created_at
                FROM saves s
                JOIN blipps b ON b.blipp_id = s.blipp_id
                WHERE s.user_id = $1 AND s.created_at < $2
                ORDER BY s.created_at DESC
                LIMIT $3
                """,
                current_user.user_id,
                cursor_dt,
                fetch_limit,
            )
        else:
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
                    b.language,
                    b.status,
                    s.created_at AS saved_at,
                    b.created_at AS created_at
                FROM saves s
                JOIN blipps b ON b.blipp_id = s.blipp_id
                WHERE s.user_id = $1
                ORDER BY s.created_at DESC
                LIMIT $2
                """,
                current_user.user_id,
                fetch_limit,
            )

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items = []
    for r in page_rows:
        variants = r["audio_variants"]
        if isinstance(variants, str):
            try:
                variants = json.loads(variants)
            except Exception:
                variants = {}
        elif variants is None:
            variants = {}

        items.append(
            SavedBlippItem(
                blipp_id=r["blipp_id"],
                creator_id=r["creator_id"],
                title=r["title"],
                description=r["description"],
                audio_url=r["audio_url"],
                audio_variants=variants,
                duration_seconds=r["duration_seconds"] or 0.0,
                language=r["language"] or "en",
                status=r["status"] or "published",
                saved_at=r["saved_at"].isoformat() if r["saved_at"] else None,
                created_at=r["created_at"].isoformat() if r["created_at"] else None,
            )
        )

    next_cursor = (
        encode_cursor(page_rows[-1]["saved_at"], str(page_rows[-1]["blipp_id"]))
        if (has_more and page_rows and page_rows[-1]["saved_at"])
        else None
    )

    return SavedBlippsResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/blipps/{blipp_id}/save", response_model=SaveActionResponse, status_code=status.HTTP_200_OK)
async def save_blipp(
    blipp_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Saves/bookmarks a Blipp for the authenticated user (§5.3).
    Idempotent operation that records the bookmark and emits an engagement.save event.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        # Verify blipp exists
        blipp_exists = await conn.fetchval(
            "SELECT 1 FROM blipps WHERE blipp_id = $1",
            blipp_id,
        )
        if not blipp_exists:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="BLIPP_NOT_FOUND",
                message=f"Blipp '{blipp_id}' not found",
            )

        # Idempotent insert into saves table
        await conn.execute(
            """
            INSERT INTO saves (user_id, blipp_id, created_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, blipp_id) DO NOTHING
            """,
            current_user.user_id,
            blipp_id,
            now,
        )

    # Publish engagement event to NATS JetStream ENGAGEMENT stream (§5.8)
    try:
        event_payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "save",
            "user_id": str(current_user.user_id),
            "blipp_id": str(blipp_id),
            "session_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "position_seconds": 0.0,
        }
        await event_bus.publish(
            subject="engagement.save",
            payload=event_payload,
        )
        logger.info(f"Published engagement.save: user {current_user.user_id} saved blipp {blipp_id}")
    except Exception as e:
        logger.warning(f"Failed to publish engagement.save event to NATS: {e}")

    return SaveActionResponse(status="saved", blipp_id=blipp_id)


@router.delete("/blipps/{blipp_id}/save", response_model=SaveActionResponse, status_code=status.HTTP_200_OK)
async def unsave_blipp(
    blipp_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Removes a saved/bookmarked Blipp for the authenticated user (§5.3).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        res = await conn.execute(
            "DELETE FROM saves WHERE user_id = $1 AND blipp_id = $2",
            current_user.user_id,
            blipp_id,
        )

    if res == "DELETE 1":
        event_payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "unsave",
            "user_id": str(current_user.user_id),
            "blipp_id": str(blipp_id),
            "session_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "position_seconds": 0.0,
        }
        try:
            await event_bus.publish("engagement.unsave", event_payload)
        except Exception as e:
            logger.warning(f"Failed to publish engagement.unsave event to NATS: {e}")

    logger.info(f"Removed saved blipp {blipp_id} for user {current_user.user_id}")
    return SaveActionResponse(status="unsaved", blipp_id=blipp_id)
