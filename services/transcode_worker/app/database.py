import json
import uuid
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncpg

from app.config import settings

logger = logging.getLogger("transcode-worker.database")

_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _pool is not None:
        pool_loop = getattr(_pool, "_loop", None)
        if pool_loop and (pool_loop.is_closed() or (current_loop and pool_loop != current_loop)):
            _pool = None

    if _pool is None:
        await init_db()
    return _pool


async def init_db() -> None:
    global _pool
    if _pool is not None:
        return

    candidate_databases = [settings.POSTGRES_DB, "blipp", "keycloak", "postgres"]
    connected = False

    for db_name in candidate_databases:
        try:
            logger.info(f"Connecting to PostgreSQL at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{db_name}")
            _pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=db_name,
                min_size=1,
                max_size=5,
                timeout=10.0,
            )
            connected = True
            logger.info(f"PostgreSQL connection pool initialized on database '{db_name}'")
            break
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL database '{db_name}': {e}")

    if not connected or _pool is None:
        raise RuntimeError("Could not establish PostgreSQL connection pool")


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


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
