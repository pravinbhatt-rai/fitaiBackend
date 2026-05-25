from __future__ import annotations

import json
from typing import Any
from functools import wraps
import redis.asyncio as aioredis
from utils.config import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def cache_get(key: str) -> Any | None:
    try:
        r = await get_redis()
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("cache.get.error", key=key, error=str(exc))
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    try:
        r = await get_redis()
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception as exc:
        logger.warning("cache.set.error", key=key, error=str(exc))


async def cache_delete(key: str) -> None:
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception as exc:
        logger.warning("cache.delete.error", key=key, error=str(exc))


def cached(prefix: str, ttl: int = 300):
    """Async decorator that caches JSON-serialisable return values in Redis."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            key = f"{prefix}:{':'.join(str(a) for a in args)}"
            hit = await cache_get(key)
            if hit is not None:
                logger.debug("cache.hit", key=key)
                return hit
            result = await fn(*args, **kwargs)
            await cache_set(key, result, ttl)
            return result
        return wrapper
    return decorator
