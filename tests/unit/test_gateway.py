"""Gateway behaviour with an injected clock, sleep and jitter: no real waiting."""

import asyncio

import pytest

from app.services.llm.base import (
    LLMAuthError,
    LLMBadRequestError,
    LLMCircuitOpenError,
    LLMConfigError,
    LLMContentError,
    LLMOverloadedError,
    LLMRateLimitError,
    LLMRequest,
    LLMServerError,
    LLMTimeoutError,
)
from app.services.llm.circuit_breaker import CircuitBreaker, CircuitState
from app.services.llm.gateway import LLMGateway
from app.services.llm.mock import MockProvider

REQUEST = LLMRequest(question="What is Redis?")


class FakeTime:
    """A clock that only moves when the gateway 'sleeps'."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_gateway(primary, fallback=None, fake=None, **kwargs) -> LLMGateway:
    fake = fake or FakeTime()
    defaults = {
        "timeout_seconds": 0.05,
        "overall_deadline_seconds": 100.0,
        "max_retries": 2,
        "backoff_base_seconds": 1.0,
        "backoff_max_seconds": 8.0,
        "breaker_failure_threshold": 5,
        "sleep": fake.sleep,
        "rand": lambda: 1.0,  # jitter pinned to its maximum => delays are the caps
        "clock": fake.clock,
    }
    return LLMGateway(primary, fallback, **{**defaults, **kwargs})


async def test_success_first_try():
    primary = MockProvider()
    outcome = await make_gateway(primary).generate(REQUEST)
    assert outcome.result.text.startswith("[mock]")
    assert (outcome.retries, outcome.fallback_used, primary.calls) == (0, False, 1)


async def test_retries_with_exponential_backoff_then_succeeds():
    primary, fake = MockProvider(), FakeTime()
    primary.script("server_error", "server_error", "ok")
    outcome = await make_gateway(primary, fake=fake).generate(REQUEST)
    assert outcome.retries == 2 and primary.calls == 3
    assert fake.sleeps == [1.0, 2.0]  # base * 2**attempt with jitter factor 1.0


async def test_jitter_scales_the_delay():
    primary, fake = MockProvider(), FakeTime()
    primary.script("server_error", "ok")
    await make_gateway(primary, fake=fake, rand=lambda: 0.25).generate(REQUEST)
    assert fake.sleeps == [0.25]


async def test_retries_are_bounded():
    primary = MockProvider()
    primary.script(*["server_error"] * 10)
    with pytest.raises(LLMServerError) as excinfo:
        await make_gateway(primary).generate(REQUEST)
    assert primary.calls == 3  # 1 attempt + max_retries(2)
    assert excinfo.value.retries_used == 2


async def test_timeout_is_retried_then_raised():
    primary = MockProvider()
    primary.script("timeout", "timeout", "timeout")
    with pytest.raises(LLMTimeoutError):
        await make_gateway(primary).generate(REQUEST)
    assert primary.calls == 3


@pytest.mark.parametrize(
    ("behaviour", "error"), [("auth_error", LLMAuthError), ("bad_request", LLMBadRequestError)]
)
async def test_non_retryable_errors_are_not_retried(behaviour, error):
    primary = MockProvider()
    primary.script(behaviour, "ok")
    with pytest.raises(error):
        await make_gateway(primary).generate(REQUEST)
    assert primary.calls == 1


async def test_content_error_is_retried_only_once():
    primary = MockProvider()
    primary.script("empty", "empty", "ok")
    with pytest.raises(LLMContentError):
        await make_gateway(primary).generate(REQUEST)
    assert primary.calls == 2


async def test_rate_limit_honours_retry_after():
    primary, fake = MockProvider(), FakeTime()
    primary.retry_after = 3.0
    primary.script("rate_limit", "ok")
    outcome = await make_gateway(primary, fake=fake).generate(REQUEST)
    assert fake.sleeps == [3.0] and outcome.retries == 1


async def test_no_retry_beyond_overall_deadline():
    primary, fake = MockProvider(), FakeTime()
    primary.retry_after = 30.0  # provider asks for longer than we are willing to wait
    primary.script("rate_limit", "ok")
    with pytest.raises(LLMRateLimitError):
        await make_gateway(primary, fake=fake, overall_deadline_seconds=10.0).generate(REQUEST)
    assert primary.calls == 1 and fake.sleeps == []


async def test_fallback_after_primary_exhausted():
    primary, fallback = MockProvider(), MockProvider(default_model="fallback-model")
    fallback.name = "mock_fallback"
    primary.script(*["server_error"] * 3)
    request = LLMRequest(question="q", model="mock-2")
    outcome = await make_gateway(primary, fallback).generate(request)
    assert outcome.fallback_used and outcome.result.provider == "mock_fallback"
    assert outcome.result.model == "fallback-model"  # the fallback uses its own model
    assert outcome.retries == 2


async def test_auth_error_falls_back_without_retry():
    primary, fallback = MockProvider(), MockProvider()
    fallback.name = "mock_fallback"
    primary.script("auth_error")
    outcome = await make_gateway(primary, fallback).generate(REQUEST)
    assert outcome.fallback_used and primary.calls == 1


async def test_bad_request_does_not_fall_back():
    primary, fallback = MockProvider(), MockProvider()
    fallback.name = "mock_fallback"
    primary.script("bad_request")
    with pytest.raises(LLMBadRequestError):
        await make_gateway(primary, fallback).generate(REQUEST)
    assert fallback.calls == 0


async def test_unconfigured_provider_raises_config_error():
    class Unconfigured(MockProvider):
        @property
        def configured(self) -> bool:
            return False

    primary = Unconfigured()
    with pytest.raises(LLMConfigError):
        await make_gateway(primary).generate(REQUEST)
    assert primary.calls == 0


async def test_circuit_opens_and_fails_fast_then_recovers():
    primary, fake = MockProvider(), FakeTime()
    gateway = make_gateway(
        primary, fake=fake, max_retries=0, breaker_failure_threshold=3, breaker_reset_seconds=30.0
    )
    primary.script(*["server_error"] * 3)
    for _ in range(3):
        with pytest.raises(LLMServerError):
            await gateway.generate(REQUEST)
    assert gateway.breaker_state("mock") is CircuitState.OPEN

    with pytest.raises(LLMCircuitOpenError):
        await gateway.generate(REQUEST)
    assert primary.calls == 3  # the open circuit did not call the provider

    fake.now += 31  # reset window passes: one trial call is allowed and succeeds
    await gateway.generate(REQUEST)
    assert gateway.breaker_state("mock") is CircuitState.CLOSED


async def test_concurrency_limit_sheds_load():
    primary = MockProvider(latency_seconds=0.2)
    gateway = LLMGateway(primary, max_concurrency=1, queue_wait_seconds=0.01, timeout_seconds=1)
    first = asyncio.create_task(gateway.generate(REQUEST))
    await asyncio.sleep(0.05)  # the first call now holds the only slot
    with pytest.raises(LLMOverloadedError):
        await gateway.generate(REQUEST)
    assert (await first).result.text


def test_circuit_breaker_transitions():
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=10, clock=lambda: now[0])
    assert breaker.allow() and breaker.state is CircuitState.CLOSED
    breaker.record_failure()
    breaker.record_success()  # a success resets the consecutive-failure count
    breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN and not breaker.allow()

    now[0] = 10.0
    assert breaker.allow() and breaker.state is CircuitState.HALF_OPEN
    assert not breaker.allow()  # only one trial call at a time
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN  # failed trial re-opens

    now[0] = 20.0
    assert breaker.allow()
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
