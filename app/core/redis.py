from contextlib import asynccontextmanager
from typing import AsyncIterator
import redis.asyncio as aioredis
from app.core.config import get_settings
from app.core.logging import get_logger

logger=get_logger(__name__)
_redis_pool: aioredis.ConnectionPool|None=None

def get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        settings=get_settings()
        _redis_pool=aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
    return _redis_pool

async def get_redis() -> AsyncIterator[aioredis.Redis]:
    pool=get_redis_pool()
    client=aioredis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()

async def close_redis_pool():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool=None
        logger.info("redis_pool_closed")