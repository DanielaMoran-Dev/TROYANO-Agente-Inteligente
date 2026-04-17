"""
Redis Service — cache and pub/sub broker for the real-time chat.
"""

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
