"""Redis response cache for /chat.

The key is a SHA-256 over everything that can change the answer. The user id
is part of it: one user's cached answer is never served to another user, at
the price of a lower hit rate. Only successful answers are stored, with a
short TTL. Any Redis failure is treated as a cache miss (fail open): the
cache is an optimisation and must never take /chat down.
"""

import hashlib
import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.monitoring import metrics

logger = logging.getLogger(__name__)


def build_cache_key(
    *,
    user_id: str,
    question: str,
    provider: str,
    model: str,
    temperature: float,
    prompt_version: str,
    use_rag: bool,
    kb_version: str,
) -> str:
    # Collapse whitespace and case so trivially different spellings share an entry.
    normalized = " ".join(question.lower().split())
    material = json.dumps(
        [user_id, normalized, provider, model, temperature, prompt_version, use_rag, kb_version]
    )
    return "cache:chat:" + hashlib.sha256(material.encode()).hexdigest()


class ResponseCache:
    def __init__(self, redis: Redis, ttl_seconds: int, enabled: bool = True) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._enabled = enabled

    async def get(self, key: str) -> dict | None:
        if not self._enabled:
            return None
        try:
            raw = await self._redis.get(key)
        except RedisError:
            logger.warning("cache_unavailable", extra={"operation": "get"})
            raw = None
        metrics.CACHE_REQUESTS.labels(result="hit" if raw else "miss").inc()
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: dict) -> None:
        if not self._enabled:
            return
        try:
            await self._redis.set(key, json.dumps(value), ex=self._ttl)
        except RedisError:
            logger.warning("cache_unavailable", extra={"operation": "set"})
