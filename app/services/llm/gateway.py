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

        # One circuit breaker per provider. Each breaker reports its state to a
        # Prometheus gauge whenever it changes.
        providers = [primary]
        if fallback is not None:
            providers.append(fallback)
        self._breakers: dict[str, CircuitBreaker] = {}
        for provider in providers:
            gauge = metrics.LLM_CIRCUIT_STATE.labels(provider=provider.name)
            gauge.set(CircuitState.CLOSED)
            self._breakers[provider.name] = CircuitBreaker(
                breaker_failure_threshold,
                breaker_reset_seconds,
                clock=clock,
                on_state_change=gauge.set,
            )

    def breaker_state(self, provider_name: str) -> CircuitState:
        return self._breakers[provider_name].state

    async def generate(self, request: LLMRequest) -> GatewayResult:
        deadline = self._clock() + self._deadline
        await self._acquire_slot()
        try:
            try:
                result, retries = await self._call_with_retries(self.primary, request, deadline)
                return GatewayResult(result=result, retries=retries, fallback_used=False)
            except LLMBadRequestError:
                raise  # the request itself is wrong: another provider will not help
            except LLMError as primary_error:
                if self.fallback is None:
                    raise
                logger.warning(
                    "llm_fallback",
                    extra={"provider": self.fallback.name, "error_code": primary_error.code},
                )
                # The requested model name belongs to the primary provider; the
                # fallback always uses its own configured default.
                fallback_request = replace(request, model=None)
                result, fallback_retries = await self._call_with_retries(
                    self.fallback, fallback_request, deadline
                )
                metrics.LLM_FALLBACKS.inc()
                return GatewayResult(
                    result=result,
                    retries=primary_error.retries_used + fallback_retries,
                    fallback_used=True,
                )
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
        """Call one provider, retrying retryable errors. Returns (result, retries used)."""
        retries = 0
        while True:
            try:
                result = await self._call_once(provider, request, deadline)
                return result, retries
            except LLMError as error:
                self._count_failure(provider.name, error)
                delay = self._retry_delay(error, retries)
                out_of_retries = retries >= self._allowed_retries(error)
                too_late = self._clock() + delay >= deadline
                if out_of_retries or too_late:
                    error.retries_used = retries
                    raise

            retries += 1
            metrics.LLM_RETRIES.labels(provider=provider.name).inc()
            logger.info("llm_retry", extra={"provider": provider.name, "attempt": retries})
            await self._sleep(delay)

    def _allowed_retries(self, error: LLMError) -> int:
        if not error.retryable:
            return 0
        if isinstance(error, LLMContentError):
            return min(1, self._max_retries)  # an empty answer is retried once at most
        return self._max_retries

    async def _call_once(
        self, provider: LLMProvider, request: LLMRequest, deadline: float
    ) -> LLMResult:
        """Make a single provider call. Raises an LLMError subclass on any failure."""
        name = provider.name
        breaker = self._breakers[name]
        if not provider.configured:
            raise LLMConfigError(f"provider '{name}' is not configured")
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise LLMTimeoutError("overall deadline exceeded")
        if not breaker.allow():
            raise LLMCircuitOpenError(f"circuit open for '{name}'")

        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                provider.generate(request), timeout=min(self._timeout, remaining)
            )
        except TimeoutError as exc:
            breaker.record_failure()
            raise LLMTimeoutError("provider call timed out") from exc
        except LLMError as error:
            if isinstance(error, _BREAKER_FAILURES):
                breaker.record_failure()
            else:
                breaker.release_trial()
            if isinstance(error, LLMAuthError):
                logger.critical("llm_auth_failed", extra={"provider": name})
            raise
        finally:
            metrics.LLM_DURATION.labels(provider=name).observe(time.perf_counter() - started)

        breaker.record_success()
        metrics.LLM_REQUESTS.labels(provider=name, outcome="success").inc()
        if result.prompt_tokens is not None:
            metrics.LLM_TOKENS.labels(provider=name, type="prompt").inc(result.prompt_tokens)
        if result.completion_tokens is not None:
            metrics.LLM_TOKENS.labels(provider=name, type="completion").inc(
                result.completion_tokens
            )
        return result

    @staticmethod
    def _count_failure(provider_name: str, error: LLMError) -> None:
        metrics.LLM_REQUESTS.labels(provider=provider_name, outcome="failure").inc()
        metrics.LLM_FAILURES.labels(provider=provider_name, error_type=type(error).__name__).inc()

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
