"""LLM gateway: the one place that decides how a provider call may fail.

How this works, for one ``generate`` call:

1. Concurrency limit. A semaphore caps in-flight LLM calls in this process.
   A request waits at most ``queue_wait_seconds`` for a slot, then is shed
   (``LLMOverloadedError``) instead of queueing without bound.
2. Overall deadline. Fixed when the call starts; every later decision checks
   it, so retries can never make a request run longer than promised.
3. For each provider in the chain (primary, then optional fallback):
   the circuit breaker is consulted, the call runs under a per-attempt timeout,
   and retryable failures are retried with exponential backoff and full jitter.
4. If the primary fails for good, the fallback provider is tried. If that
   fails too, the last error is raised and the web layer maps it to HTTP.

``sleep``, ``rand`` and ``clock`` are injected so unit tests run instantly and
deterministically.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from app.monitoring import metrics
from app.services.llm.base import (
    LLMAuthError,
    LLMBadRequestError,
    LLMCircuitOpenError,
    LLMConfigError,
    LLMContentError,
    LLMError,
    LLMOverloadedError,
    LLMProvider,
    LLMRateLimitError,
    LLMRequest,
    LLMResult,
    LLMServerError,
    LLMTimeoutError,
)
from app.services.llm.circuit_breaker import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)

# Failures that say "the provider is unhealthy" and therefore count towards
# opening the circuit. A rejected request or an empty answer does not.
_BREAKER_FAILURES = (LLMTimeoutError, LLMServerError, LLMRateLimitError, LLMAuthError)


@dataclass(frozen=True, slots=True)
class GatewayResult:
    result: LLMResult
    retries: int
    fallback_used: bool


class LLMGateway:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
        *,
        timeout_seconds: float = 15.0,
        overall_deadline_seconds: float = 40.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.5,
        backoff_max_seconds: float = 8.0,
        max_concurrency: int = 20,
        queue_wait_seconds: float = 5.0,
        breaker_failure_threshold: int = 5,
        breaker_reset_seconds: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self._timeout = timeout_seconds
        self._deadline = overall_deadline_seconds
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._queue_wait = queue_wait_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._sleep = sleep
        self._rand = rand
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}
        for provider in self._chain():
            gauge = metrics.LLM_CIRCUIT_STATE.labels(provider=provider.name)
            gauge.set(CircuitState.CLOSED)
            self._breakers[provider.name] = CircuitBreaker(
                breaker_failure_threshold,
                breaker_reset_seconds,
                clock=clock,
                on_state_change=lambda state, g=gauge: g.set(state),
            )

    def _chain(self) -> list[LLMProvider]:
        return [self.primary] + ([self.fallback] if self.fallback else [])

    def breaker_state(self, provider_name: str) -> CircuitState:
        return self._breakers[provider_name].state

    async def generate(self, request: LLMRequest) -> GatewayResult:
        deadline = self._clock() + self._deadline
        await self._acquire_slot()
        try:
            retries = 0
            last_error: LLMError | None = None
            for index, provider in enumerate(self._chain()):
                # The requested model name belongs to the primary provider; the
                # fallback always uses its own configured default.
                attempt_request = request if index == 0 else replace(request, model=None)
                if index > 0:
                    logger.warning(
                        "llm_fallback",
                        extra={"provider": provider.name, "error_code": last_error.code},
                    )
                try:
                    result, used = await self._call_with_retries(
                        provider, attempt_request, deadline
                    )
                except LLMBadRequestError:
                    raise  # the request itself is wrong: another provider will not help
                except LLMError as exc:
                    last_error = exc
                    retries += exc.retries_used
                    continue
                if index > 0:
                    metrics.LLM_FALLBACKS.inc()
                return GatewayResult(result=result, retries=retries + used, fallback_used=index > 0)
            raise last_error or LLMConfigError("no LLM provider is configured")
        finally:
            self._semaphore.release()

    async def _acquire_slot(self) -> None:
        if self._semaphore.locked() and self._queue_wait <= 0:
            raise LLMOverloadedError("no free LLM slot")
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self._queue_wait or None)
        except TimeoutError as exc:
            raise LLMOverloadedError("timed out waiting for an LLM slot") from exc

    async def _call_with_retries(
        self, provider: LLMProvider, request: LLMRequest, deadline: float
    ) -> tuple[LLMResult, int]:
        breaker = self._breakers[provider.name]
        attempt = 0
        while True:
            error = await self._attempt(provider, breaker, request, deadline)
            if isinstance(error, LLMResult):
                return error, attempt

            # Content errors get one retry; other retryable errors get the full budget.
            allowed = 0
            if error.retryable:
                allowed = (
                    min(1, self._max_retries)
                    if isinstance(error, LLMContentError)
                    else self._max_retries
                )
            delay = self._retry_delay(error, attempt)
            if attempt >= allowed or self._clock() + delay >= deadline:
                error.retries_used = attempt
                raise error

            attempt += 1
            metrics.LLM_RETRIES.labels(provider=provider.name).inc()
            logger.info(
                "llm_retry",
                extra={"provider": provider.name, "attempt": attempt, "error_code": error.code},
            )
            await self._sleep(delay)

    async def _attempt(
        self,
        provider: LLMProvider,
        breaker: CircuitBreaker,
        request: LLMRequest,
        deadline: float,
    ) -> LLMResult | LLMError:
        """Make one call. Returns the result, or the error (never raises LLMError)."""
        name = provider.name
        if not provider.configured:
            return self._failed(name, LLMConfigError(f"provider '{name}' is not configured"))
        remaining = deadline - self._clock()
        if remaining <= 0:
            return self._failed(name, LLMTimeoutError("overall deadline exceeded"))
        if not breaker.allow():
            return self._failed(name, LLMCircuitOpenError(f"circuit open for '{name}'"))

        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                provider.generate(request), timeout=min(self._timeout, remaining)
            )
        except TimeoutError:
            error: LLMError = LLMTimeoutError("provider call timed out")
        except LLMError as exc:
            error = exc
        else:
            breaker.record_success()
            metrics.LLM_DURATION.labels(provider=name).observe(time.perf_counter() - started)
            metrics.LLM_REQUESTS.labels(provider=name, outcome="success").inc()
            for kind, count in (
                ("prompt", result.prompt_tokens),
                ("completion", result.completion_tokens),
            ):
                if count is not None:
                    metrics.LLM_TOKENS.labels(provider=name, type=kind).inc(count)
            return result

        metrics.LLM_DURATION.labels(provider=name).observe(time.perf_counter() - started)
        if isinstance(error, _BREAKER_FAILURES):
            breaker.record_failure()
        else:
            breaker.release_trial()
        if isinstance(error, LLMAuthError):
            logger.critical("llm_auth_failed", extra={"provider": name})
        return self._failed(name, error)

    @staticmethod
    def _failed(provider_name: str, error: LLMError) -> LLMError:
        metrics.LLM_REQUESTS.labels(provider=provider_name, outcome="failure").inc()
        metrics.LLM_FAILURES.labels(provider=provider_name, error_type=type(error).__name__).inc()
        return error

    def _retry_delay(self, error: LLMError, attempt: int) -> float:
        """Honour the provider's Retry-After; otherwise exponential backoff with full jitter.

        Full jitter (a uniformly random delay between 0 and the exponential
        cap) spreads retries out so many clients that failed together do not
        all come back at the same instant.
        """
        if isinstance(error, LLMRateLimitError) and error.retry_after is not None:
            return error.retry_after
        cap = min(self._backoff_max, self._backoff_base * (2**attempt))
        return self._rand() * cap
