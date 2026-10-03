"""Rate limiter, login throttle and cache logic against fakeredis."""

import fakeredis
import pytest

from app.core.errors import RateLimitedError, ServiceUnavailableError
from app.services.cache import ResponseCache, build_cache_key
from app.services.rate_limiter import (
    ChatRateLimiter,
    InProcessLimiter,
    LoginThrottle,
    RateLimiter,
)

KEY_ARGS = {
    "user_id": "u1",
    "question": "What is Redis?",
    "provider": "mock",
    "model": "mock-1",
    "temperature": 0.2,
    "prompt_version": "v1",
    "use_rag": True,
    "kb_version": "0",
}


def new_redis(server=None):
    return fakeredis.FakeAsyncRedis(server=server or fakeredis.FakeServer(), decode_responses=True)


async def test_fixed_window_counts_and_resets():
    now = [1000.0]
    limiter = RateLimiter(new_redis(), clock=lambda: now[0])
    results = [await limiter.hit("chat", "u1", limit=2, window=60) for _ in range(3)]
    assert [r.allowed for r in results] == [True, True, False]
    assert [r.remaining for r in results] == [1, 0, 0]
    assert 1 <= results[-1].retry_after <= 61

    now[0] += 60  # next window: the counter starts again
    assert (await limiter.hit("chat", "u1", limit=2, window=60)).allowed


async def test_limit_is_per_identity():
    limiter = RateLimiter(new_redis())
    assert (await limiter.hit("chat", "u1", 1, 60)).allowed
    assert not (await limiter.hit("chat", "u1", 1, 60)).allowed
    assert (await limiter.hit("chat", "u2", 1, 60)).allowed


async def test_limit_is_shared_between_replicas():
    """Two limiter instances with separate connections = two API replicas."""
    server = fakeredis.FakeServer()
    replica_a = ChatRateLimiter(new_redis(server), limit=3, window=60)
    replica_b = ChatRateLimiter(new_redis(server), limit=3, window=60)
    await replica_a.check("u1")
    await replica_b.check("u1")
    await replica_a.check("u1")
    with pytest.raises(RateLimitedError) as excinfo:
        await replica_b.check("u1")  # 4th request overall, although only 2nd on replica B
    assert int(excinfo.value.headers["Retry-After"]) >= 1


async def test_chat_limiter_fails_open_with_local_cap_when_redis_is_down():
    server = fakeredis.FakeServer()
    limiter = ChatRateLimiter(new_redis(server), limit=2, window=60)
    server.connected = False
    await limiter.check("u1")  # allowed: fail open
    await limiter.check("u1")
    with pytest.raises(RateLimitedError):
        await limiter.check("u1")  # ...but the in-process cap still applies


def test_in_process_limiter_window():
    now = [0.0]
    limiter = InProcessLimiter(clock=lambda: now[0])
    assert limiter.hit("u1", 1, 10).allowed
    assert not limiter.hit("u1", 1, 10).allowed
    now[0] = 10.0
    assert limiter.hit("u1", 1, 10).allowed


async def test_login_throttle_locks_and_resets():
    throttle = LoginThrottle(new_redis(), max_attempts=2, lockout_seconds=300)
    await throttle.ensure_not_locked("alice", "1.1.1.1")
    await throttle.record_failure("alice", "1.1.1.1")
    await throttle.record_failure("Alice", "1.1.1.1")  # usernames are case-insensitive
    with pytest.raises(RateLimitedError) as excinfo:
        await throttle.ensure_not_locked("alice", "1.1.1.1")
    assert 1 <= int(excinfo.value.headers["Retry-After"]) <= 300
    await throttle.ensure_not_locked("alice", "2.2.2.2")  # another IP is not locked

    await throttle.reset("alice", "1.1.1.1")
    await throttle.ensure_not_locked("alice", "1.1.1.1")


async def test_login_throttle_fails_closed_when_redis_is_down():
    server = fakeredis.FakeServer()
    throttle = LoginThrottle(new_redis(server), max_attempts=2, lockout_seconds=300)
    server.connected = False
    with pytest.raises(ServiceUnavailableError):
        await throttle.ensure_not_locked("alice", "1.1.1.1")


def test_cache_key_normalises_question():
    assert build_cache_key(**KEY_ARGS) == build_cache_key(
        **{**KEY_ARGS, "question": "  what   is REDIS? "}
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", "u2"),
        ("model", "mock-2"),
        ("temperature", 0.9),
        ("prompt_version", "v2"),
        ("provider", "openai_compatible"),
        ("use_rag", False),
        ("kb_version", "1"),
        ("question", "What is Qdrant?"),
    ],
)
def test_cache_key_isolation(field, value):
    assert build_cache_key(**KEY_ARGS) != build_cache_key(**{**KEY_ARGS, field: value})


async def test_cache_roundtrip_ttl_and_fail_open():
    server = fakeredis.FakeServer()
    redis = new_redis(server)
    cache = ResponseCache(redis, ttl_seconds=600)
    assert await cache.get("cache:chat:k") is None
    await cache.set("cache:chat:k", {"answer": "42"})
    assert await cache.get("cache:chat:k") == {"answer": "42"}
    assert 0 < await redis.ttl("cache:chat:k") <= 600

    server.connected = False  # Redis down => behaves like a miss, never raises
    assert await cache.get("cache:chat:k") is None
    await cache.set("cache:chat:k", {"answer": "43"})


async def test_cache_can_be_disabled():
    cache = ResponseCache(new_redis(), ttl_seconds=600, enabled=False)
    await cache.set("k", {"answer": "42"})
    assert await cache.get("k") is None
