"""
Redis Service — cache and pub/sub broker for the real-time chat.
"""

import json
import os
import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis pool created (%s)", REDIS_URL)
    return _pool


def get_client() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=get_pool())


async def publish(channel: str, message: str):
    async with get_client() as r:
        await r.publish(channel, message)


async def subscribe(channel: str):
    """Return a pubsub object subscribed to channel."""
    r = get_client()
    ps = r.pubsub()
    await ps.subscribe(channel)
    return ps


async def cache_get(key: str) -> dict | list | None:
    """Return cached JSON value or None on miss / Redis error."""
    try:
        async with get_client() as r:
            raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("cache_get(%s) failed: %s", key, exc)
        return None


async def cache_set(key: str, value: dict | list, ttl: int) -> None:
    """Store JSON value with TTL (seconds). Silently no-ops on Redis error."""
    try:
        payload = json.dumps(value, ensure_ascii=False)
        async with get_client() as r:
            await r.set(key, payload, ex=ttl)
    except Exception as exc:
        logger.warning("cache_set(%s) failed: %s", key, exc)
