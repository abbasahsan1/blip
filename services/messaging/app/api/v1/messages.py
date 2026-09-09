import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from blipp_common.database import get_db_pool
from blipp_common.exceptions import AppException
from blipp_common.security import AuthenticatedUser, get_current_user
from app.models.messaging import (
    DMMessageResponse,
    DMThreadResponse,
    MessageCreateRequest,
    MessageListResponse,
    ThreadCreateRequest,
)

logger = logging.getLogger("messaging.api.messages")
router = APIRouter(prefix="/messages", tags=["Direct Messaging & Blipp Sharing"])


@router.post("/threads", response_model=DMThreadResponse, status_code=status.HTTP_200_OK)
async def get_or_create_thread(
    body: ThreadCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates or retrieves an existing direct messaging thread between the
    authenticated caller and the target recipient_id (§5.4).
    """
    if current_user.user_id == body.recipient_id:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CANNOT_DM_SELF",
            message="Cannot start a direct message thread with yourself",
        )

    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        # Search for existing thread between these two exact participants
        row = await conn.fetchrow(
            """
            SELECT thread_id, participant_ids, created_at, updated_at
            FROM dm_threads
            WHERE participant_ids @> ARRAY[$1::uuid, $2::uuid]
              AND array_length(participant_ids, 1) = 2
            LIMIT 1
            """,
            current_user.user_id,
            body.recipient_id,
        )

        if row:
            # Thread already exists: retrieve latest message
            latest_msg_row = await conn.fetchrow(
                """
                SELECT message_id, thread_id, sender_id, message_type, blipp_id, body, created_at
                FROM dm_messages
                WHERE thread_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                row["thread_id"],
            )
            latest_message = DMMessageResponse.model_validate(dict(latest_msg_row)) if latest_msg_row else None
            return DMThreadResponse(
                thread_id=row["thread_id"],
                participant_ids=list(row["participant_ids"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                latest_message=latest_message,
            )

        # Create new thread
        new_thread_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        participant_ids = [current_user.user_id, body.recipient_id]

        await conn.execute(
            """
            INSERT INTO dm_threads (thread_id, participant_ids, created_at, updated_at)
            VALUES ($1, $2, $3, $3)
            """,
            new_thread_id,
            participant_ids,
            now,
        )

        logger.info(f"Created new DM thread {new_thread_id} between {current_user.user_id} and {body.recipient_id}")
        return DMThreadResponse(
            thread_id=new_thread_id,
            participant_ids=participant_ids,
            created_at=now,
            updated_at=now,
            latest_message=None,
        )


@router.get("/threads", response_model=List[DMThreadResponse])
async def list_threads(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Lists active DM threads for the authenticated user, ordered by latest message (§5.4).
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                t.thread_id, 
                t.participant_ids, 
                t.created_at, 
                t.updated_at,
                m.message_id,
                m.sender_id,
                m.message_type,
                m.blipp_id,
                m.body,
                m.created_at AS message_created_at
            FROM dm_threads t
            LEFT JOIN LATERAL (
                SELECT message_id, sender_id, message_type, blipp_id, body, created_at
                FROM dm_messages
                WHERE thread_id = t.thread_id
                ORDER BY created_at DESC
                LIMIT 1
            ) m ON true
            WHERE $1::uuid = ANY(t.participant_ids)
            ORDER BY COALESCE(m.created_at, t.updated_at, t.created_at) DESC
            LIMIT $2 OFFSET $3
            """,
            current_user.user_id,
            limit,
            offset,
        )

        threads = []
        for r in rows:
            latest_message = None
            if r["message_id"]:
                latest_message = DMMessageResponse(
                    message_id=r["message_id"],
                    thread_id=r["thread_id"],
                    sender_id=r["sender_id"],
                    message_type=r["message_type"],
                    blipp_id=r["blipp_id"],
                    body=r["body"],
                    created_at=r["message_created_at"],
                )
            threads.append(
                DMThreadResponse(
                    thread_id=r["thread_id"],
                    participant_ids=list(r["participant_ids"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    latest_message=latest_message,
                )
            )

        return threads


@router.post("/threads/{thread_id}", response_model=DMMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    thread_id: uuid.UUID,
    body: MessageCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Sends a message in an existing DM thread (§5.4).
    Validates that the authenticated caller is one of the thread participants.
    Supports plain text and sharing a blipp_id.
    """
    # Validate payload semantics
    if body.message_type == "blipp_share" and not body.blipp_id:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_MESSAGE_PAYLOAD",
            message="A blipp_id is required when message_type is 'blipp_share'",
        )
    if body.message_type == "text" and not (body.body and body.body.strip()):
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_MESSAGE_PAYLOAD",
            message="Message body text cannot be empty for text messages",
        )

    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        thread = await conn.fetchrow(
            "SELECT thread_id, participant_ids FROM dm_threads WHERE thread_id = $1",
            thread_id,
        )
        if not thread:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="THREAD_NOT_FOUND",
                message=f"Thread '{thread_id}' not found",
            )

        participants = list(thread["participant_ids"])
        if current_user.user_id not in participants:
            raise AppException(
                status_code=status.HTTP_403_FORBIDDEN,
                code="NOT_A_PARTICIPANT",
                message="You are not a participant in this conversation thread",
            )

        message_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        await conn.execute(
            """
            INSERT INTO dm_messages (
                message_id, thread_id, sender_id, message_type, blipp_id, body, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            message_id,
            thread_id,
            current_user.user_id,
            body.message_type,
            body.blipp_id,
            body.body.strip() if body.body else None,
            now,
        )

        # Update thread's updated_at timestamp
        await conn.execute(
            "UPDATE dm_threads SET updated_at = $1 WHERE thread_id = $2",
            now,
            thread_id,
        )

        logger.info(f"Message {message_id} sent by {current_user.user_id} in thread {thread_id}")

        return DMMessageResponse(
            message_id=message_id,
            thread_id=thread_id,
            sender_id=current_user.user_id,
            message_type=body.message_type,
            blipp_id=body.blipp_id,
            body=body.body.strip() if body.body else None,
            created_at=now,
        )


@router.get("/threads/{thread_id}", response_model=MessageListResponse)
async def get_thread_messages(
    thread_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="ISO timestamp cursor for backward pagination"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns cursor-paginated message history for a direct messaging thread (§5.4).
    Validates that the authenticated caller is one of the thread participants.
    """
    pool = await get_db_pool()
    if not pool:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_UNAVAILABLE",
            message="Database connection pool unavailable",
        )

    async with pool.acquire() as conn:
        thread = await conn.fetchrow(
            "SELECT thread_id, participant_ids FROM dm_threads WHERE thread_id = $1",
            thread_id,
        )
        if not thread:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code="THREAD_NOT_FOUND",
                message=f"Thread '{thread_id}' not found",
            )

        participants = list(thread["participant_ids"])
        if current_user.user_id not in participants:
            raise AppException(
                status_code=status.HTTP_403_FORBIDDEN,
                code="NOT_A_PARTICIPANT",
                message="You are not a participant in this conversation thread",
            )

        fetch_limit = limit + 1
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except ValueError:
                raise AppException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="INVALID_CURSOR",
                    message="Cursor must be a valid ISO 8601 datetime string",
                )
            rows = await conn.fetch(
                """
                SELECT message_id, thread_id, sender_id, message_type, blipp_id, body, created_at
                FROM dm_messages
                WHERE thread_id = $1 AND created_at < $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                thread_id,
                cursor_dt,
                fetch_limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT message_id, thread_id, sender_id, message_type, blipp_id, body, created_at
                FROM dm_messages
                WHERE thread_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                thread_id,
                fetch_limit,
            )

        has_more = len(rows) > limit
        items_rows = rows[:limit]

        items = [
            DMMessageResponse(
                message_id=r["message_id"],
                thread_id=r["thread_id"],
                sender_id=r["sender_id"],
                message_type=r["message_type"],
                blipp_id=r["blipp_id"],
                body=r["body"],
                created_at=r["created_at"],
            )
            for r in items_rows
        ]

        next_cursor = items[-1].created_at.isoformat() if (has_more and items) else None

        return MessageListResponse(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )
