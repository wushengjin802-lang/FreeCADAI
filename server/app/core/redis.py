"""Redis client helpers."""

from functools import lru_cache

import redis

from server.app.core.config import settings


@lru_cache(maxsize=1)
def get_redis_client():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def redis_ping():
    try:
        return bool(get_redis_client().ping())
    except Exception:
        return False
