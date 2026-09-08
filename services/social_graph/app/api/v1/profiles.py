import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, status

from blipp_common.database import get_db_pool
from blipp_common.exceptions import AppException
from blipp_common.security import (
    AuthenticatedUser,
    get_current_user,
    get_optional_current_user,
)
from app.models.profile import (
    ProfileCreate,
    ProfileResponse,
    ProfileUpdate,
)

logger = logging.getLogger("social-graph.api.profiles")
router = APIRouter(prefix="/profiles", tags=["User Profiles"])


async def _get_social_counts_and_following(
    conn, target_user_id: uuid.UUID, caller_user_id: Optional[uuid.UUID] = None
) -> tuple[int, int, bool]:
    """Helper to compute followers_count, following_count, and is_following."""
    followers_count = await conn.fetchval(
        "SELECT COUNT(*) FROM follows WHERE followee_id = $1", target_user_id
    ) or 0

    following_count = await conn.fetchval(
        "SELECT COUNT(*) FROM follows WHERE follower_id = $1", target_user_id
    ) or 0

    is_following = False
    if caller_user_id and caller_user_id != target_user_id:
        val = await conn.fetchval(
            "SELECT 1 FROM follows WHERE follower_id = $1 AND followee_id = $2",
            caller_user_id,
            target_user_id,
        )
        is_following = bool(val)

    return followers_count, following_count, is_following


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def claim_username(
    profile_data: ProfileCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Claims a unique username and initializes the user's social profile (§6.1).
    Returns 409 Conflict if username is already taken or if the user already has a profile.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    requested_username = profile_data.username.strip().lower()
    display_name = (profile_data.display_name or "").strip() or requested_username
    bio = profile_data.bio.strip() if profile_data.bio else None
    avatar_url = profile_data.avatar_url.strip() if profile_data.avatar_url else None

    async with pool.acquire() as conn:
        # 1. Check if authenticated user already has an active profile
        existing_profile = await conn.fetchrow(
            "SELECT user_id, username FROM users_profile WHERE user_id = $1",
            current_user.user_id,
        )
        if existing_profile:
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                code="PROFILE_ALREADY_EXISTS",
                message=f"User already has a profile with username '{existing_profile['username']}'",
            )

        # 2. Check if requested username is taken by another user (case-insensitive)
        taken = await conn.fetchrow(
            "SELECT user_id FROM users_profile WHERE LOWER(username) = $1",
            requested_username,
        )
        if taken:
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                code="USERNAME_TAKEN",
                message=f"Username '{requested_username}' is already taken",
            )

        # 3. Insert new profile
        row = await conn.fetchrow(
            """
            INSERT INTO users_profile (
                user_id, username, display_name, bio, avatar_url, is_creator, verification_status, created_at
            )
            VALUES ($1, $2, $3, $4, $5, FALSE, 'unverified', NOW())
            RETURNING user_id, username, display_name, bio, avatar_url, is_creator, verification_status, created_at
            """,
            current_user.user_id,
            requested_username,
            display_name,
            bio,
            avatar_url,
        )

    return ProfileResponse(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        bio=row["bio"],
        avatar_url=row["avatar_url"],
        is_creator=row["is_creator"],
        verification_status=row["verification_status"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        followers_count=0,
        following_count=0,
        is_following=False,
    )


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Fetches the authenticated user's profile and live follower/following counts.
    Returns 404 Not Found if the user has not completed the username claiming flow (§6.1).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, username, display_name, bio, avatar_url, is_creator, verification_status, created_at
            FROM users_profile
            WHERE user_id = $1
            """,
            current_user.user_id,
        )

        if not row:
            # Fallback for seeded users: If current_user has a username claim in token and no conflict exists, auto-claim
            if current_user.username and current_user.username != str(current_user.user_id):
                display_name = current_user.first_name or current_user.username
                row = await conn.fetchrow(
                    """
                    INSERT INTO users_profile (user_id, username, display_name, bio, avatar_url, is_creator, verification_status)
                    VALUES ($1, $2, $3, NULL, NULL, FALSE, 'unverified')
                    ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
                    RETURNING user_id, username, display_name, bio, avatar_url, is_creator, verification_status, created_at
                    """,
                    current_user.user_id,
                    current_user.username.lower(),
                    display_name,
                )
            else:
                raise AppException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="PROFILE_NOT_FOUND",
                    message="Profile not found. Please claim a username via POST /v1/profiles",
                )

        followers_count, following_count, _ = await _get_social_counts_and_following(
            conn, current_user.user_id, current_user.user_id
        )

    return ProfileResponse(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        bio=row["bio"],
        avatar_url=row["avatar_url"],
        is_creator=row["is_creator"],
        verification_status=row["verification_status"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        followers_count=followers_count,
        following_count=following_count,
        is_following=False,
    )


@router.patch("/me", response_model=ProfileResponse)
async def update_my_profile(
    update_data: ProfileUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Updates mutable profile attributes (display name, bio, avatar URL) for the authenticated user.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    fields = []
    values = []
    idx = 1

    if update_data.display_name is not None:
        fields.append(f"display_name = ${idx}")
        values.append(update_data.display_name.strip() or None)
        idx += 1

    if update_data.bio is not None:
        fields.append(f"bio = ${idx}")
        values.append(update_data.bio.strip() if update_data.bio else None)
        idx += 1

    if update_data.avatar_url is not None:
        fields.append(f"avatar_url = ${idx}")
        values.append(update_data.avatar_url.strip() if update_data.avatar_url else None)
        idx += 1

    async with pool.acquire() as conn:
        # Check profile exists
        existing = await conn.fetchrow(
            "SELECT user_id FROM users_profile WHERE user_id = $1",
            current_user.user_id,
        )
        if not existing:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="PROFILE_NOT_FOUND",
                message="Profile not found. Please claim a username first",
            )

        if fields:
            values.append(current_user.user_id)
            query = f"""
                UPDATE users_profile
                SET {', '.join(fields)}
                WHERE user_id = ${idx}
                RETURNING user_id, username, display_name, bio, avatar_url, is_creator, verification_status, created_at
            """
            row = await conn.fetchrow(query, *values)
        else:
            row = await conn.fetchrow(
                """
                SELECT user_id, username, display_name, bio, avatar_url, is_creator, verification_status, created_at
                FROM users_profile
                WHERE user_id = $1
                """,
                current_user.user_id,
            )

        followers_count, following_count, _ = await _get_social_counts_and_following(
            conn, current_user.user_id, current_user.user_id
        )

    return ProfileResponse(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        bio=row["bio"],
        avatar_url=row["avatar_url"],
        is_creator=row["is_creator"],
        verification_status=row["verification_status"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        followers_count=followers_count,
        following_count=following_count,
        is_following=False,
    )


@router.get("/{username}", response_model=ProfileResponse)
async def get_profile_by_username(
    username: str,
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_current_user),
):
    """
    Public profile lookup by unique username (case-insensitive).
    Calculates followers_count, following_count, and is_following relative to the requesting caller.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    clean_username = username.strip().lower()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, username, display_name, bio, avatar_url, is_creator, verification_status, created_at
            FROM users_profile
            WHERE LOWER(username) = $1
            """,
            clean_username,
        )

        if not row:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="USER_NOT_FOUND",
                message=f"User '{username}' not found",
            )

        caller_id = current_user.user_id if current_user else None
        followers_count, following_count, is_following = await _get_social_counts_and_following(
            conn, row["user_id"], caller_id
        )

    return ProfileResponse(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        bio=row["bio"],
        avatar_url=row["avatar_url"],
        is_creator=row["is_creator"],
        verification_status=row["verification_status"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following,
    )
