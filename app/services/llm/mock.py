"""Deterministic mock provider: the default, needs no API key or network.

It lets the whole platform (auth, rate limiting, caching, RAG, persistence,
metrics) run and be tested without paying for an LLM. Its answers are clearly
prefixed ``[mock]`` so they can never be mistaken for a real model's output.

Tests script failures with ``provider.script("timeout", "ok")``: each call
consumes the next scripted behaviour, and an empty script means success.
"""

import asyncio
import time
from collections import deque

from app.services.llm.base import (
    LLMAuthError,
    LLMBadRequestError,
    LLMContentError,
    LLMRateLimitError,
    LLMRequest,
    LLMResult,
    LLMServerError,
    build_user_message,
)

BEHAVIOURS = {"ok", "timeout", "server_error", "rate_limit", "auth_error", "bad_request", "empty"}


class MockProvider:
    name = "mock"

    def __init__(self, latency_seconds: float = 0.0, default_model: str = "mock-1") -> None:
        self.default_model = default_model
        self.latency_seconds = latency_seconds
        self.calls = 0
        self.retry_after: float | None = 1.0  # value sent with a scripted "rate_limit"
        self._script: deque[str] = deque()

    @property
    def configured(self) -> bool:
        return True

    def script(self, *behaviours: str) -> None:
        unknown = set(behaviours) - BEHAVIOURS
        if unknown:
            raise ValueError(f"Unknown mock behaviours: {sorted(unknown)}")
        self._script = deque(behaviours)

    async def healthcheck(self) -> bool:
        return True

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        started = time.perf_counter()
        behaviour = self._script.popleft() if self._script else "ok"

        if behaviour == "timeout":
            await asyncio.sleep(3600)  # the gateway's per-attempt timeout cancels this
        if behaviour == "server_error":
            raise LLMServerError("mock 500")
        if behaviour == "rate_limit":
            raise LLMRateLimitError("mock 429", retry_after=self.retry_after)
        if behaviour == "auth_error":
            raise LLMAuthError("mock 401")
        if behaviour == "bad_request":
            raise LLMBadRequestError("mock 400")
        if behaviour == "empty":
            raise LLMContentError("mock returned an empty completion")

        if self.latency_seconds:
            await asyncio.sleep(self.latency_seconds)

        if request.context:
            text = f"[mock] Based on the knowledge base: {request.context[0][:400]}"
        else:
            text = f"[mock] You asked: {request.question[:200]}"

        # Whitespace word counts stand in for tokens. They are a simulation, the
        # same way the answer is; real adapters pass through the provider's numbers.
        prompt_tokens = len(build_user_message(request).split())
        completion_tokens = len(text.split())
        return LLMResult(
            text=text,
            provider=self.name,
            model=request.model or self.default_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
