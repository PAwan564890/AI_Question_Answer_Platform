"""Redis-backed rate limiting, shared by every API replica.

Why Redis: a counter kept in one process's memory is invisible to the other
replicas, so with N replicas a user would get N times the limit. Redis gives
all replicas one shared counter.

Algorithm: fixed window. The key contains the window number
(``now // window``), so each window gets a fresh counter that expires by
itself. ``INCR`` + ``EXPIRE`` are sent in one MULTI/EXEC transaction: the
increment is atomic, so two replicas can never both read "19" and both allow
request number 20. Known trade-off: a burst straddling a window boundary can
reach up to 2x the limit; a sliding window or token bucket fixes that at the
cost of more complexity.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import RateLimitedError, ServiceUnavailableError
from app.monitoring import metrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # seconds until the current window ends


class RateLimiter:
    """Distributed fixed-window counter. Raises RedisError if Redis is down."""

    def __init__(self, redis: Redis, clock: Callable[[], float] = time.time) -> None:
        self._redis = redis
        self._clock = clock

    async def hit(self, scope: str, identity: str, limit: int, window: int) -> RateLimitResult:
        now = self._clock()
        window_id = int(now // window)
        key = f"rl:{scope}:{identity}:{window_id}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window + 1)
            count, _ = await pipe.execute()
        retry_after = int((window_id + 1) * window - now) + 1
        return RateLimitResult(count <= limit, limit, max(0, limit - count), retry_after)


class InProcessLimiter:
    """Per-process fallback used only while Redis is unreachable.

    It cannot coordinate replicas (the effective limit becomes ``limit x
    replicas``) but it still bounds what one user can do to one process.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._counts: dict[tuple[str, int], int] = {}

    def hit(self, identity: str, limit: int, window: int) -> RateLimitResult:
        now = self._clock()
        window_id = int(now // window)
        # Drop counters from past windows so the dict cannot grow forever.
        self._counts = {k: v for k, v in self._counts.items() if k[1] == window_id}
        count = self._counts.get((identity, window_id), 0) + 1
        self._counts[(identity, window_id)] = count
        retry_after = int((window_id + 1) * window - now) + 1
        return RateLimitResult(count <= limit, limit, max(0, limit - count), retry_after)


class ChatRateLimiter:
    """Per-user /chat limit. Failure policy: FAIL OPEN with a local cap.

    If Redis is down we prefer to keep answering questions (availability) and
    accept weaker abuse protection for the duration, bounded by the in-process
    fallback. The outage is visible in logs, /health and ``dependency_up``.
    """

    def __init__(self, redis: Redis, limit: int, window: int) -> None:
        self._limiter = RateLimiter(redis)
        self._fallback = InProcessLimiter()
        self._limit = limit
        self._window = window

    async def check(self, user_id: str) -> None:
        try:
            result = await self._limiter.hit("chat", user_id, self._limit, self._window)
            metrics.DEPENDENCY_UP.labels(dependency="redis").set(1)
        except RedisError:
            logger.error("rate_limiter_redis_unavailable", extra={"policy": "fail_open_local_cap"})
            metrics.DEPENDENCY_UP.labels(dependency="redis").set(0)
            result = self._fallback.hit(user_id, self._limit, self._window)
        if not result.allowed:
            metrics.RATE_LIMIT_EVENTS.labels(scope="chat").inc()
            logger.warning("chat_rate_limited", extra={"user_id": user_id})
            raise RateLimitedError(result.retry_after, "Chat rate limit exceeded.")


class LoginThrottle:
    """Brute-force protection per username + client IP. Failure policy: FAIL CLOSED.

    Only failed attempts are counted. After ``max_attempts`` failures the pair
    is locked until the counter expires. If Redis is down logins are refused
    (503): an attacker must not get unlimited password guesses just because
    the throttle store is unavailable. Already-issued tokens keep working.
    """

    def __init__(self, redis: Redis, max_attempts: int, lockout_seconds: int) -> None:
        self._redis = redis
        self._max_attempts = max_attempts
        self._lockout = lockout_seconds

    @staticmethod
    def _key(username: str, ip: str) -> str:
        return f"rl:login:{username.lower()}:{ip}"

    async def ensure_not_locked(self, username: str, ip: str) -> None:
        key = self._key(username, ip)
        try:
            attempts = int(await self._redis.get(key) or 0)
            ttl = await self._redis.ttl(key) if attempts >= self._max_attempts else 0
        except RedisError as exc:
            logger.error("login_throttle_redis_unavailable", extra={"policy": "fail_closed"})
            metrics.DEPENDENCY_UP.labels(dependency="redis").set(0)
            raise ServiceUnavailableError("Login is temporarily unavailable.") from exc
        if attempts >= self._max_attempts:
            metrics.RATE_LIMIT_EVENTS.labels(scope="login").inc()
            raise RateLimitedError(max(ttl, 1), "Too many failed login attempts. Try again later.")

    async def record_failure(self, username: str, ip: str) -> None:
        key = self._key(username, ip)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, self._lockout)
                await pipe.execute()
        except RedisError:
            logger.error("login_throttle_redis_unavailable", extra={"policy": "fail_closed"})

    async def reset(self, username: str, ip: str) -> None:
        try:
            await self._redis.delete(self._key(username, ip))
        except RedisError:
            logger.warning("login_throttle_reset_failed")
