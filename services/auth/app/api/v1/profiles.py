import logging
from typing import Optional
from fastapi import APIRouter, Depends, status
from blipp_common.security import get_current_user, AuthenticatedUser
from blipp_common.database import get_db_pool
from blipp_common.exceptions import AppException
from app.models.profile import UserProfileResponse, UserProfileUpdate


logger = logging.getLogger("auth-service.api.profiles")

router = APIRouter(prefix="/profiles", tags=["User Profiles"])


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: AuthenticatedUser = Depends(get_current_user)):
    """
    Returns the profile for the authenticated user.
    If none exists, creates a default profile using Keycloak claims.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, username, display_name, bio, avatar_url, created_at
            FROM users_profile
            WHERE user_id = $1
            """,
            current_user.user_id,
        )

        if not row:
            username = current_user.username or str(current_user.user_id)
            display_name = current_user.first_name or username
            row = await conn.fetchrow(
                """
                INSERT INTO users_profile (user_id, username, display_name, bio, avatar_url)
                VALUES ($1, $2, $3, NULL, NULL)
                ON CONFLICT (user_id) DO UPDATE
                    SET username = EXCLUDED.username
                RETURNING user_id, username, display_name, bio, avatar_url, created_at
                """,
                current_user.user_id,
                username,
                display_name,
            )

    return UserProfileResponse(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        bio=row["bio"],
        avatar_url=row["avatar_url"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    update_data: UserProfileUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Allows updating display_name, bio, and avatar_url for the authenticated user.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool unavailable",
        )

    # Ensure profile exists first
    await get_my_profile(current_user)

    fields = []
    values = []
    idx = 1

    if update_data.display_name is not None:
        fields.append(f"display_name = ${idx}")
        values.append(update_data.display_name.strip())
        idx += 1

    if update_data.bio is not None:
        fields.append(f"bio = ${idx}")
        values.append(update_data.bio.strip() if update_data.bio else None)
        idx += 1

    if update_data.avatar_url is not None:
        fields.append(f"avatar_url = ${idx}")
        values.append(update_data.avatar_url.strip() if update_data.avatar_url else None)
        idx += 1

    if not fields:
        # No updates provided, return current profile
        return await get_my_profile(current_user)

    values.append(current_user.user_id)
    query = f"""
        UPDATE users_profile
        SET {', '.join(fields)}
        WHERE user_id = ${idx}
        RETURNING user_id, username, display_name, bio, avatar_url, created_at
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *values)

    return UserProfileResponse(
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        bio=row["bio"],
        avatar_url=row["avatar_url"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )
