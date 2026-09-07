import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.security import get_current_user
from app.core.database import get_db_pool
from app.core.storage import storage_service
from app.core.exceptions import AppException
from app.models.schemas import (
    TokenData,
    ListeningHistoryItem,
    ListeningHistoryResponse,
    CreatorAnalyticsResponse,
    CreatorTopBlipp,
)

logger = logging.getLogger("auth-service.api.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics & Playback History"])


@router.get("/history", response_model=ListeningHistoryResponse, status_code=status.HTTP_200_OK)
async def get_listening_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Returns paginated playback history for the authenticated user,
    including completion status and listened duration.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool is unavailable",
        )

    try:
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM listening_session_agg
                WHERE user_id = $1
                """,
                current_user.user_id,
            )

            rows = await conn.fetch(
                """
                SELECT 
                    l.session_id,
                    l.blipp_id,
                    b.title,
                    b.description,
                    b.audio_url,
                    b.duration_seconds,
                    l.total_seconds_listened,
                    l.completed,
                    l.drop_off_position_seconds,
                    l.session_date,
                    b.creator_id,
                    COALESCE(u.display_name, u.username, 'Creator') AS creator_name,
                    u.username AS creator_username
                FROM listening_session_agg l
                JOIN blipps b ON l.blipp_id = b.blipp_id
                LEFT JOIN users_profile u ON b.creator_id = u.user_id
                WHERE l.user_id = $1
                ORDER BY l.session_date DESC, l.total_seconds_listened DESC
                LIMIT $2 OFFSET $3
                """,
                current_user.user_id,
                limit,
                offset,
            )
    except Exception as e:
        logger.exception(f"Error fetching listening history: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="QUERY_ERROR",
            message="Failed to retrieve listening history",
        )

    items = []
    for r in rows:
        playback_url = storage_service.get_playback_url(r["audio_url"])
        items.append(
            ListeningHistoryItem(
                session_id=r["session_id"],
                blipp_id=r["blipp_id"],
                title=r["title"],
                description=r["description"],
                audio_url=playback_url,
                duration_seconds=float(r["duration_seconds"] or 0.0),
                total_seconds_listened=float(r["total_seconds_listened"] or 0.0),
                completed=bool(r["completed"]),
                drop_off_position_seconds=float(r["drop_off_position_seconds"]) if r["drop_off_position_seconds"] is not None else None,
                session_date=r["session_date"].isoformat() if hasattr(r["session_date"], "isoformat") else str(r["session_date"]),
                creator_id=r["creator_id"],
                creator_name=r["creator_name"],
                creator_username=r["creator_username"],
            )
        )

    return ListeningHistoryResponse(items=items, total=total or 0)


@router.get("/creator", response_model=CreatorAnalyticsResponse, status_code=status.HTTP_200_OK)
async def get_creator_analytics(
    current_user: TokenData = Depends(get_current_user),
):
    """
    Returns summary statistics for the authenticated creator:
    total listen minutes across all Blipps, completed play count,
    total plays, and top-performing Blipps.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database pool is unavailable",
        )

    try:
        async with pool.acquire() as conn:
            # 1. Total minutes listened
            total_minutes = await conn.fetchval(
                """
                SELECT COALESCE(SUM(total_minutes_listened), 0.0)
                FROM creator_minutes_agg
                WHERE creator_id = $1
                """,
                current_user.user_id,
            )

            # 2. Total plays and completed plays across all blipps owned by this creator
            plays_row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) AS total_plays,
                    COUNT(*) FILTER (WHERE l.completed = TRUE) AS completed_play_count
                FROM listening_session_agg l
                JOIN blipps b ON l.blipp_id = b.blipp_id
                WHERE b.creator_id = $1
                """,
                current_user.user_id,
            )

            total_plays = plays_row["total_plays"] if plays_row else 0
            completed_plays = plays_row["completed_play_count"] if plays_row else 0

            # 3. Top-performing blipps
            top_rows = await conn.fetch(
                """
                SELECT 
                    b.blipp_id,
                    b.title,
                    COALESCE(c_agg.total_mins, 0.0) AS total_minutes_listened,
                    COALESCE(l_agg.play_cnt, 0) AS play_count,
                    COALESCE(l_agg.comp_cnt, 0) AS completed_count
                FROM blipps b
                LEFT JOIN (
                    SELECT blipp_id, SUM(total_minutes_listened) AS total_mins
                    FROM creator_minutes_agg
                    WHERE creator_id = $1
                    GROUP BY blipp_id
                ) c_agg ON b.blipp_id = c_agg.blipp_id
                LEFT JOIN (
                    SELECT 
                        blipp_id,
                        COUNT(*) AS play_cnt,
                        COUNT(*) FILTER (WHERE completed = TRUE) AS comp_cnt
                    FROM listening_session_agg
                    GROUP BY blipp_id
                ) l_agg ON b.blipp_id = l_agg.blipp_id
                WHERE b.creator_id = $1
                ORDER BY total_minutes_listened DESC, play_count DESC
                LIMIT 10
                """,
                current_user.user_id,
            )
    except Exception as e:
        logger.exception(f"Error fetching creator analytics: {e}")
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="QUERY_ERROR",
            message="Failed to retrieve creator analytics",
        )

    top_blipps = [
        CreatorTopBlipp(
            blipp_id=r["blipp_id"],
            title=r["title"],
            total_minutes_listened=round(float(r["total_minutes_listened"] or 0.0), 2),
            play_count=int(r["play_count"] or 0),
            completed_count=int(r["completed_count"] or 0),
        )
        for r in top_rows
    ]

    return CreatorAnalyticsResponse(
        creator_id=current_user.user_id,
        total_listen_minutes=round(float(total_minutes or 0.0), 2),
        completed_play_count=int(completed_plays or 0),
        total_plays=int(total_plays or 0),
        top_blipps=top_blipps,
    )
