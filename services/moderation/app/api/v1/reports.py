import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from blipp_common.database import get_db_pool
from blipp_common.exceptions import AppException
from blipp_common.pagination import decode_cursor, encode_cursor
from blipp_common.security import AuthenticatedUser, get_current_user
from app.models.moderation import (
    CreateReportRequest,
    CreateReportResponse,
    ReportResponse,
    ReportsListResponse,
    REPORT_STATUSES,
)

logger = logging.getLogger("moderation.api.reports")
router = APIRouter(tags=["User Reporting"])


@router.post(
    "/reports",
    response_model=CreateReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit user report against a blipp",
)
async def create_report(
    payload: CreateReportRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    User Reporting Intake (§5.5, §6.7).
    Authenticated endpoint accepting blipp_id and reason.
    Creates a new Report record with status = 'open'.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    report_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reports (report_id, reporter_id, blipp_id, creator_id, reason, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'open', $6)
            """,
            report_id,
            current_user.user_id,
            payload.blipp_id,
            payload.creator_id,
            payload.reason,
            now,
        )

    logger.info(
        f"Report {report_id} lodged by user {current_user.user_id} against blipp {payload.blipp_id} (reason='{payload.reason}')"
    )

    return CreateReportResponse(report_id=report_id, status="open")


@router.get(
    "/reports",
    response_model=ReportsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get paginated list of reports",
)
async def list_reports(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by report status ('open', 'reviewed', 'actioned', 'dismissed')"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    cursor: Optional[str] = Query(None, description="Cursor for keyset pagination"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Paginated list of reports filtered by status for moderation dashboards (§6.7).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    if status_filter and status_filter.lower() not in REPORT_STATUSES:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_STATUS",
            message=f"Status filter must be one of: {sorted(list(REPORT_STATUSES))}",
        )

    cursor_dt = None
    if cursor:
        decoded = decode_cursor(cursor)
        if decoded:
            cursor_dt, _ = decoded
        else:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except ValueError:
                pass

    async with pool.acquire() as conn:
        if status_filter:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM reports WHERE status = $1",
                status_filter.lower(),
            )
            if cursor_dt:
                rows = await conn.fetch(
                    """
                    SELECT report_id, reporter_id, blipp_id, creator_id, reason, status, created_at
                    FROM reports
                    WHERE status = $1 AND created_at < $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    status_filter.lower(),
                    cursor_dt,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT report_id, reporter_id, blipp_id, creator_id, reason, status, created_at
                    FROM reports
                    WHERE status = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    status_filter.lower(),
                    limit,
                    offset,
                )
        else:
            total = await conn.fetchval("SELECT COUNT(*) FROM reports")
            if cursor_dt:
                rows = await conn.fetch(
                    """
                    SELECT report_id, reporter_id, blipp_id, creator_id, reason, status, created_at
                    FROM reports
                    WHERE created_at < $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    cursor_dt,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT report_id, reporter_id, blipp_id, creator_id, reason, status, created_at
                    FROM reports
                    ORDER BY created_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit,
                    offset,
                )

    items = [
        ReportResponse(
            report_id=r["report_id"],
            reporter_id=r["reporter_id"],
            blipp_id=r["blipp_id"],
            creator_id=r["creator_id"],
            reason=r["reason"],
            status=r["status"],
            created_at=r["created_at"].isoformat() if r["created_at"] else None,
        )
        for r in rows
    ]

    next_cursor = (
        encode_cursor(rows[-1]["created_at"], str(rows[-1]["report_id"]))
        if (rows and rows[-1]["created_at"] and len(rows) == limit)
        else None
    )

    return ReportsListResponse(
        items=items,
        total=total or 0,
        limit=limit,
        offset=offset,
        next_cursor=next_cursor,
    )

