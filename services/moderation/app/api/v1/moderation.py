import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, status

from blipp_common.database import get_db_pool
from blipp_common.events import event_bus
from blipp_common.exceptions import AppException
from blipp_common.security import AuthenticatedUser, get_current_user
from app.models.moderation import (
    ActionReportRequest,
    ActionReportResponse,
)

logger = logging.getLogger("moderation.api.moderation")
router = APIRouter(prefix="/moderation", tags=["Moderation Actions"])


@router.post(
    "/reports/{report_id}/action",
    response_model=ActionReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Action or dismiss a moderation report",
)
async def action_report(
    report_id: uuid.UUID,
    payload: ActionReportRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Action & Takedown Flow (§5.5, §6.7).
    - Accepts action decision: 'actioned' or 'dismissed'.
    - If dismissed: updates report status to 'dismissed'.
    - If actioned:
      1. Transitions report status to 'actioned'.
      2. Creates a Strike record for the creator of the reported Blipp.
      3. Publishes takedown event to NATS JetStream (subject: content.takedown).
      4. Auto-suspension check: Counts total strikes for creator_id within 90 days.
         If strike count >= 3, publishes account suspension event to NATS (subject: user.account.suspended).
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
        report_row = await conn.fetchrow(
            """
            SELECT report_id, reporter_id, blipp_id, creator_id, reason, status
            FROM reports
            WHERE report_id = $1
            """,
            report_id,
        )

        if not report_row:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="REPORT_NOT_FOUND",
                message=f"Report '{report_id}' not found",
            )

        blipp_id = report_row["blipp_id"]
        action_decision = payload.action.lower()

        # Handle 'dismissed' action
        if action_decision == "dismissed":
            await conn.execute(
                """
                UPDATE reports
                SET status = 'dismissed'
                WHERE report_id = $1
                """,
                report_id,
            )
            logger.info(f"Report {report_id} dismissed by moderator {current_user.user_id}")
            return ActionReportResponse(
                report_id=report_id,
                status="dismissed",
                action="dismissed",
                message="Report dismissed with no penalty",
            )

        # Handle 'actioned' action
        strike_reason = payload.reason or report_row["reason"] or "community_guidelines"
        creator_id = payload.creator_id or report_row["creator_id"]

        # Update report status to 'actioned'
        await conn.execute(
            """
            UPDATE reports
            SET status = 'actioned'
            WHERE report_id = $1
            """,
            report_id,
        )

        strike_id: Optional[uuid.UUID] = None
        strikes_count_90d: int = 0
        account_suspended: bool = False

        if creator_id:
            strike_id = uuid.uuid4()
            # 1. Create strike record
            await conn.execute(
                """
                INSERT INTO strikes (strike_id, creator_id, blipp_id, reason, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                strike_id,
                creator_id,
                blipp_id,
                strike_reason,
                now,
            )
            logger.info(
                f"Issued strike {strike_id} against creator {creator_id} for blipp {blipp_id} (reason='{strike_reason}')"
            )

            # 2. Auto-suspension check: 90 days strike count
            strikes_count_90d = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM strikes
                WHERE creator_id = $1 AND created_at >= NOW() - INTERVAL '90 days'
                """,
                creator_id,
            ) or 0

            logger.info(f"Creator {creator_id} has {strikes_count_90d} strike(s) in the past 90 days")

            if strikes_count_90d >= 3:
                account_suspended = True
                logger.warning(
                    f"Creator {creator_id} exceeded strike threshold ({strikes_count_90d} >= 3)! Publishing account suspension..."
                )
                try:
                    await event_bus.publish(
                        subject="user.account.suspended",
                        payload={
                            "user_id": str(creator_id),
                            "reason": "strike_threshold_exceeded",
                            "strikes_count": strikes_count_90d,
                            "timestamp": now.isoformat(),
                        },
                    )
                    logger.info(f"Published user.account.suspended for user {creator_id}")
                except Exception as e:
                    logger.error(f"Failed to publish user.account.suspended to NATS: {e}")

    # 3. Publish takedown event to NATS JetStream on stream UPLOADS
    try:
        await event_bus.publish(
            subject="content.takedown",
            payload={
                "blipp_id": str(blipp_id),
                "reason": strike_reason,
                "report_id": str(report_id),
                "creator_id": str(creator_id) if creator_id else None,
                "timestamp": now.isoformat(),
            },
        )
        logger.info(f"Published content.takedown for blipp {blipp_id}")
    except Exception as e:
        logger.error(f"Failed to publish content.takedown to NATS: {e}")

    return ActionReportResponse(
        report_id=report_id,
        status="actioned",
        action="actioned",
        strike_id=strike_id,
        creator_id=creator_id,
        strikes_count_90d=strikes_count_90d,
        account_suspended=account_suspended,
        message="Report actioned: content takedown initiated and strike registered",
    )
