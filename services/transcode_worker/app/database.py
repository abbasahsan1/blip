import json
import uuid
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncpg

from blipp_common.database import (
    get_db_pool as _common_get_db_pool,
    init_db_pool as _common_init_db_pool,
    close_db_pool as _common_close_db_pool,
)
from app.config import settings

logger = logging.getLogger("transcode-worker.database")


async def get_db_pool() -> asyncpg.Pool:
    """Returns the shared asyncpg connection pool initialized with transcode worker settings."""
    return await _common_get_db_pool(settings)


async def init_db() -> None:
    """Initializes the database connection pool and applies unified table DDL."""
    await _common_init_db_pool(settings)


async def close_db() -> None:
    """Closes the asyncpg connection pool."""
    await _common_close_db_pool()


async def update_upload_status(upload_id: uuid.UUID, status: str) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE uploads
            SET processing_status = $2
            WHERE upload_id = $1
            """,
            upload_id,
            status,
        )


async def get_upload(upload_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT upload_id, creator_id, raw_file_url, upload_type, processing_status, title, description, created_at
            FROM uploads
            WHERE upload_id = $1
            """,
            upload_id,
        )
        return dict(row) if row else None


async def create_blipp(
    blipp_id: uuid.UUID,
    creator_id: uuid.UUID,
    title: Optional[str],
    description: Optional[str],
    audio_url: str,
    audio_variants: Dict[str, str],
    duration_seconds: float,
    source_type: str,
    parent_upload_id: uuid.UUID,
    status: str = "published",
    language: str = "en",
) -> Dict[str, Any]:
    pool = await get_db_pool()
    now_utc = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO blipps (
                blipp_id, creator_id, title, description, audio_url, audio_variants,
                duration_seconds, language, status, source_type, parent_upload_id, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (blipp_id) DO UPDATE
                SET audio_url = EXCLUDED.audio_url,
                    audio_variants = EXCLUDED.audio_variants,
                    duration_seconds = EXCLUDED.duration_seconds,
                    status = EXCLUDED.status
            RETURNING blipp_id, creator_id, title, description, audio_url, audio_variants,
                      duration_seconds, language, status, source_type, parent_upload_id, created_at
            """,
            blipp_id,
            creator_id,
            title,
            description,
            audio_url,
            json.dumps(audio_variants),
            float(duration_seconds),
            language,
            status,
            source_type,
            parent_upload_id,
            now_utc,
        )
        return dict(row) if row else {}


__all__ = [
    "get_db_pool",
    "init_db",
    "close_db",
    "update_upload_status",
    "get_upload",
    "create_blipp",
]
