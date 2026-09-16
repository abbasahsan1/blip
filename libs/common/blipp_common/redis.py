import sys
import types
import logging
from typing import Optional

# Ensure async_timeout exists for redis.asyncio in Python 3.11+ environments
if "async_timeout" not in sys.modules:
    try:
        import async_timeout
    except ImportError:
        import asyncio
        _at = types.ModuleType("async_timeout")
        _at.timeout = getattr(asyncio, "timeout", None)
        sys.modules["async_timeout"] = _at

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

from blipp_common.config import settings

logger = logging.getLogger("blipp_common.redis")

_redis_pool = None
_redis_client = None


async def get_redis_client(redis_url: Optional[str] = None):
    """
    Returns the singleton asynchronous Redis client with pooled connections.
    """
    if aioredis is None:
        logger.warning("Redis library is not installed in the current environment.")
        return None

    global _redis_pool, _redis_client
    if _redis_client is None:
        url = redis_url or settings.REDIS_URL
        try:
            _redis_pool = aioredis.ConnectionPool.from_url(
                url,
                max_connections=20,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            _redis_client = aioredis.Redis(connection_pool=_redis_pool)
            logger.info(f"Initialized Redis connection pool for {url}")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client for {url}: {e}")
            raise
    return _redis_client


async def close_redis() -> None:
    """
    Closes the singleton Redis client and disconnects the underlying connection pool.
    """
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


__all__ = ["get_redis_client", "close_redis"]
