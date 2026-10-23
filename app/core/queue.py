import asyncio

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

_pool: ArqRedis | None = None
_lock = asyncio.Lock()


def get_redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_queue() -> ArqRedis:
    """
    Connects on first use, not at app startup, on purpose: if Redis is down,
    the API should still boot and keep serving login, reads, etc. Only the
    endpoints that actually enqueue work should be affected.
    """
    global _pool
    async with _lock:
        if _pool is None:
            redis_settings = get_redis_settings()
            redis_settings.conn_retries = 1  # fail fast instead of retrying for ~5s
            _pool = await create_pool(redis_settings)
    return _pool


async def close_queue() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None