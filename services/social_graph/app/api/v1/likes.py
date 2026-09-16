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

    async with pool.acquire() as conn:
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
        try:
            await event_bus.publish(
                "engagement.like",
                {
                    "event_type": "like",
                    "user_id": str(current_user.user_id),
                    "blipp_id": str(blipp_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            # The like is durable; a transient event-bus failure must not make
            # the user retry an already recorded engagement.
            logger.warning("Failed to publish engagement.like for %s: %s", blipp_id, exc)

    return LikeActionResponse(success=True, blipp_id=blipp_id, is_liked=True)
