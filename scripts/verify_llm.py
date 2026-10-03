"""Verify the real LLM provider configured in .env with ONE live request.

    python scripts/verify_llm.py

Requires in .env:  LLM_PROVIDER=openai_compatible, OPENAI_BASE_URL, OPENAI_API_KEY,
OPENAI_MODEL. It calls the provider through the same gateway the API uses and
then exercises two failure paths. The API key is never printed.

Checks:
  1. success        - one real completion: text, model, latency, token usage
  2. bad credential - a deliberately wrong key must be classified as LLMAuthError,
                      not retried, and (with a fallback) answered by the mock
  3. timeout        - a 1 ms timeout must become LLMTimeoutError after bounded retries

Cost: checks 1 and 3 send a short prompt each (a few dozen tokens); check 3 may
be billed by the provider even though the client stops waiting.
Exit code: 0 all passed, 1 a check failed, 2 no real provider is configured.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.services.llm.base import (  # noqa: E402
    LLMAuthError,
    LLMError,
    LLMRequest,
    LLMTimeoutError,
)
from app.services.llm.gateway import LLMGateway  # noqa: E402
from app.services.llm.mock import MockProvider  # noqa: E402
from app.services.llm.openai_compat import OpenAICompatibleProvider  # noqa: E402

REQUEST = LLMRequest(question="Reply with the single word: pong", max_tokens=16, temperature=0)


def provider(settings, *, api_key: str | None = None, timeout: float | None = None):
    return OpenAICompatibleProvider(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key if api_key is None else api_key,
        model=settings.openai_model,
        timeout_seconds=timeout or settings.llm_timeout_seconds,
        max_tokens_param=settings.openai_max_tokens_param,
    )


def report(name: str, ok: bool, detail: str) -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


async def main() -> int:
    settings = get_settings()
    real = provider(settings)
    if settings.llm_provider != "openai_compatible" or not real.configured:
        print(
            "No real provider is configured (need LLM_PROVIDER=openai_compatible, "
            "OPENAI_API_KEY and OPENAI_MODEL in .env). Nothing was sent."
        )
        return 2
    print(f"Provider base URL: {settings.openai_base_url}")
    print(f"Model: {settings.openai_model}   (API key: set, {len(settings.openai_api_key)} chars)")
    results = []

    # 1. One real request through the gateway.
    try:
        outcome = await LLMGateway(real, timeout_seconds=settings.llm_timeout_seconds).generate(
            REQUEST
        )
        r = outcome.result
        results.append(
            report(
                "success",
                bool(r.text),
                f"answer={r.text[:60]!r} model={r.model} latency_ms={r.latency_ms} "
                f"retries={outcome.retries} usage=(prompt={r.prompt_tokens}, "
                f"completion={r.completion_tokens}, total={r.total_tokens})",
            )
        )
        if r.total_tokens is None:
            print("       note: this provider did not report token usage; the API returns null.")
    except LLMError as exc:
        results.append(report("success", False, f"{type(exc).__name__} ({exc.code})"))

    # 2. Wrong key: classified as an auth error, not retried, fallback answers.
    bad = provider(settings, api_key="invalid-key-for-verification")
    try:
        await LLMGateway(bad, max_retries=2).generate(REQUEST)
        results.append(report("bad credential", False, "the provider accepted an invalid key"))
    except LLMAuthError as exc:
        results.append(report("bad credential", exc.retries_used == 0, "LLMAuthError, 0 retries"))
    except LLMError as exc:
        results.append(
            report("bad credential", False, f"expected LLMAuthError, got {type(exc).__name__}")
        )
    mock = MockProvider()
    outcome = await LLMGateway(bad, mock).generate(REQUEST)
    results.append(
        report(
            "fallback",
            outcome.fallback_used and outcome.result.provider == "mock",
            f"fallback_used={outcome.fallback_used} provider={outcome.result.provider}",
        )
    )

    # 3. Timeout: 1 ms cannot succeed; retries must be bounded.
    slow = provider(settings, timeout=0.001)
    try:
        await LLMGateway(
            slow, timeout_seconds=0.001, max_retries=2, backoff_base_seconds=0.05
        ).generate(REQUEST)
        results.append(report("timeout", False, "a 1 ms timeout unexpectedly succeeded"))
    except LLMTimeoutError as exc:
        results.append(
            report(
                "timeout",
                exc.retries_used == 2,
                f"LLMTimeoutError after {exc.retries_used} retries",
            )
        )
    except LLMError as exc:
        results.append(
            report("timeout", False, f"expected LLMTimeoutError, got {type(exc).__name__}")
        )

    for p in (real, bad, slow):
        await p.aclose()
    print("RESULT:", "ALL CHECKS PASSED" if all(results) else "SOME CHECKS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
