import logging
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger("auth-service.redis")

_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    global _redis_pool, _redis_client
    if _redis_client is None:
        try:
            _redis_pool = aioredis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=20,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            _redis_client = aioredis.Redis(connection_pool=_redis_pool)
            logger.info(f"Initialized Redis connection pool for {settings.REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            raise
    return _redis_client


async def close_redis() -> None:
    global _redis_client, _redis_pool
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception as e:
            logger.warning(f"Error closing Redis client: {e}")
        _redis_client = None
    if _redis_pool is not None:
        try:
            await _redis_pool.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting Redis pool: {e}")
        _redis_pool = None
    logger.info("Redis connection pool closed")
