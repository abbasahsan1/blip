import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from blipp_common.database import get_db_pool
from blipp_common.events import event_bus
from blipp_common.exceptions import AppException
from blipp_common.security import AuthenticatedUser, get_current_user

logger = logging.getLogger("social-graph.api.likes")
router = APIRouter(prefix="/likes", tags=["Blipp Likes"])


class LikeActionResponse(BaseModel):
    success: bool
    blipp_id: uuid.UUID
    is_liked: bool


@router.post("/{blipp_id}", response_model=LikeActionResponse)
async def like_blipp(
    blipp_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Persist an idempotent like and emit an engagement event."""
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    from blipp_common.outbox import record_outbox_event

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "like",
        "user_id": str(current_user.user_id),
        "blipp_id": str(blipp_id),
        "session_id": "",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "position_seconds": 0.0,
    }

    async with pool.acquire() as conn:
        async with conn.transaction():
            inserted = await conn.execute(
                """
                INSERT INTO likes (user_id, blipp_id, created_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (user_id, blipp_id) DO NOTHING
                """,
                current_user.user_id,
                blipp_id,
            )
            if inserted == "INSERT 0 1":
                await record_outbox_event(conn, "engagement.like", event_payload)

    if inserted == "INSERT 0 1":
        try:
            await event_bus.publish("engagement.like", event_payload)
        except Exception as exc:
            logger.warning("Eager publish of engagement.like delayed (outbox will deliver): %s", exc)

    return LikeActionResponse(success=True, blipp_id=blipp_id, is_liked=True)


@router.delete("/{blipp_id}", response_model=LikeActionResponse)
async def unlike_blipp(
    blipp_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Idempotently remove a like."""
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    from blipp_common.outbox import record_outbox_event

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "unlike",
        "user_id": str(current_user.user_id),
        "blipp_id": str(blipp_id),
        "session_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "position_seconds": 0.0,
    }

    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute(
                "DELETE FROM likes WHERE user_id = $1 AND blipp_id = $2",
                current_user.user_id,
                blipp_id,
            )
            if res == "DELETE 1":
                await record_outbox_event(conn, "engagement.unlike", event_payload)

    if res == "DELETE 1":
        try:
            await event_bus.publish("engagement.unlike", event_payload)
        except Exception as exc:
            logger.warning("Eager publish of engagement.unlike delayed (outbox will deliver): %s", exc)

    logger.info("User %s unliked blipp %s", current_user.user_id, blipp_id)
    return LikeActionResponse(success=True, blipp_id=blipp_id, is_liked=False)
