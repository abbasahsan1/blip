import logging
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, Query, status

from blipp_common.database import get_db_pool
from blipp_common.events import event_bus
from blipp_common.exceptions import AppException
from blipp_common.security import (
    AuthenticatedUser,
    get_current_user,
    get_optional_current_user,
)
from app.models.profile import (
    FollowActionResponse,
    FollowerItem,
    FollowListResponse,
)

logger = logging.getLogger("social-graph.api.relationships")
router = APIRouter(prefix="/social", tags=["Relationships & Follows Graph"])


@router.post("/follow/{user_id}", response_model=FollowActionResponse)
async def follow_user(
    user_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Follows another user (§5.2).
    - Prevents self-following
    - Handles duplicate follows gracefully (idempotent)
    - Emits engagement.follow event to NATS JetStream ENGAGEMENT stream (§5.8)
    """
    if current_user.user_id == user_id:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="SELF_FOLLOW_FORBIDDEN",
            message="You cannot follow yourself",
        )

    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        # 1. Verify target user exists
        target = await conn.fetchrow(
            "SELECT user_id FROM users_profile WHERE user_id = $1",
            user_id,
        )
        if not target:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="USER_NOT_FOUND",
                message="Target user profile does not exist",
            )

        # 2. Ensure follower exists in users_profile to satisfy FK constraint
        caller = await conn.fetchrow(
            "SELECT user_id FROM users_profile WHERE user_id = $1",
            current_user.user_id,
        )
        if not caller:
            fallback_username = (current_user.username or str(current_user.user_id)).lower()
            fallback_display = current_user.first_name or fallback_username
            await conn.execute(
                """
                INSERT INTO users_profile (user_id, username, display_name, is_creator, verification_status)
                VALUES ($1, $2, $3, FALSE, 'unverified')
                ON CONFLICT (user_id) DO NOTHING
                """,
                current_user.user_id,
                fallback_username,
                fallback_display,
            )

        from blipp_common.outbox import record_outbox_event

        event_payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "follow",
            "user_id": str(current_user.user_id),
            "blipp_id": None,
            "session_id": str(uuid.uuid4()),
            "target_user_id": str(user_id),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "position_seconds": 0.0,
        }

        # 3. Insert follow relationship idempotently
        async with conn.transaction():
            insert_res = await conn.execute(
                """
                INSERT INTO follows (follower_id, followee_id, created_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (follower_id, followee_id) DO NOTHING
                """,
                current_user.user_id,
                user_id,
            )
            if insert_res == "INSERT 0 1":
                await record_outbox_event(conn, "engagement.follow", event_payload)

    # 4. If newly inserted, eagerly publish event to NATS JetStream ENGAGEMENT stream (§5.8)
    if insert_res == "INSERT 0 1":
        try:
            await event_bus.publish("engagement.follow", event_payload)
            logger.info(f"Published engagement.follow: {current_user.user_id} -> {user_id}")
        except Exception as e:
            logger.warning(f"Eager publish of engagement.follow delayed (outbox will deliver): {e}")

    return FollowActionResponse(
        success=True,
        follower_id=current_user.user_id,
        followee_id=user_id,
        is_following=True,
    )


@router.delete("/follow/{user_id}", response_model=FollowActionResponse)
async def unfollow_user(
    user_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Unfollows a user (§5.2). Idempotently removes the follow edge from follows table.
    """
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
        "event_type": "unfollow",
        "user_id": str(current_user.user_id),
        "blipp_id": None,
        "session_id": str(uuid.uuid4()),
        "target_user_id": str(user_id),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "position_seconds": 0.0,
    }

    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute(
                "DELETE FROM follows WHERE follower_id = $1 AND followee_id = $2",
                current_user.user_id,
                user_id,
            )
            if res == "DELETE 1":
                await record_outbox_event(conn, "engagement.unfollow", event_payload)

    if res == "DELETE 1":
        try:
            await event_bus.publish("engagement.unfollow", event_payload)
        except Exception as e:
            logger.warning(f"Eager publish of engagement.unfollow delayed (outbox will deliver): {e}")

    return FollowActionResponse(
        success=True,
        follower_id=current_user.user_id,
        followee_id=user_id,
        is_following=False,
    )


@router.get("/{user_id}/followers", response_model=FollowListResponse)
async def get_followers(
    user_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_current_user),
):
    """
    Returns a paginated list of users following the specified user (§5.2).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    caller_id = current_user.user_id if current_user else None

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM follows WHERE followee_id = $1",
            user_id,
        ) or 0

        rows = await conn.fetch(
            """
            SELECT 
                u.user_id,
                u.username,
                u.display_name,
                u.avatar_url,
                u.bio,
                u.is_creator,
                u.verification_status,
                f.created_at AS followed_at
            FROM follows f
            JOIN users_profile u ON f.follower_id = u.user_id
            WHERE f.followee_id = $1
            ORDER BY f.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id,
            limit,
            offset,
        )

        items = []
        for r in rows:
            is_following = False
            if caller_id and caller_id != r["user_id"]:
                val = await conn.fetchval(
                    "SELECT 1 FROM follows WHERE follower_id = $1 AND followee_id = $2",
                    caller_id,
                    r["user_id"],
                )
                is_following = bool(val)

            items.append(
                FollowerItem(
                    user_id=r["user_id"],
                    username=r["username"],
                    display_name=r["display_name"],
                    avatar_url=r["avatar_url"],
                    bio=r["bio"],
                    is_creator=r["is_creator"],
                    verification_status=r["verification_status"],
                    followed_at=r["followed_at"].isoformat() if r["followed_at"] else None,
                    is_following=is_following,
                )
            )

    return FollowListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{user_id}/following", response_model=FollowListResponse)
async def get_following(
    user_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_current_user),
):
    """
    Returns a paginated list of users that the specified user follows (§5.2).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    caller_id = current_user.user_id if current_user else None

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM follows WHERE follower_id = $1",
            user_id,
        ) or 0

        rows = await conn.fetch(
            """
            SELECT 
                u.user_id,
                u.username,
                u.display_name,
                u.avatar_url,
                u.bio,
                u.is_creator,
                u.verification_status,
                f.created_at AS followed_at
            FROM follows f
            JOIN users_profile u ON f.followee_id = u.user_id
            WHERE f.follower_id = $1
            ORDER BY f.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id,
            limit,
            offset,
        )

        items = []
        for r in rows:
            is_following = False
            if caller_id and caller_id != r["user_id"]:
                val = await conn.fetchval(
                    "SELECT 1 FROM follows WHERE follower_id = $1 AND followee_id = $2",
                    caller_id,
                    r["user_id"],
                )
                is_following = bool(val)

            items.append(
                FollowerItem(
                    user_id=r["user_id"],
                    username=r["username"],
                    display_name=r["display_name"],
                    avatar_url=r["avatar_url"],
                    bio=r["bio"],
                    is_creator=r["is_creator"],
                    verification_status=r["verification_status"],
                    followed_at=r["followed_at"].isoformat() if r["followed_at"] else None,
                    is_following=is_following,
                )
            )

    return FollowListResponse(items=items, total=total, limit=limit, offset=offset)
