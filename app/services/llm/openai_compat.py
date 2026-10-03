"""Adapter for any service that implements the OpenAI Chat Completions HTTP API.

One adapter covers OpenAI, Groq, OpenRouter, Together, a local Ollama or vLLM
server, and Gemini's OpenAI-compatible endpoint: only ``OPENAI_BASE_URL``,
``OPENAI_API_KEY`` and ``OPENAI_MODEL`` change. Plain ``httpx`` is used instead
of a vendor SDK so the request, the timeout and every error path are visible.

Its job is translation: provider HTTP outcomes become the gateway's error
classes. Provider error bodies are never forwarded to API clients.
"""

import time

import httpx

from app.services.llm.base import (
    SYSTEM_PROMPT,
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigError,
    LLMContentError,
    LLMRateLimitError,
    LLMRequest,
    LLMResult,
    LLMServerError,
    LLMTimeoutError,
    build_user_message,
)


def _parse_retry_after(value: str | None) -> float | None:
    try:
        return max(0.0, float(value)) if value else None
    except ValueError:
        return None  # HTTP-date form: ignore and fall back to normal backoff


def _raise_for_status(response: httpx.Response) -> None:
    """Translate a provider HTTP error status into the gateway's error classes."""
    status = response.status_code
    if status < 400:
        return
    if status in (401, 403):
        raise LLMAuthError(f"provider rejected credentials ({status})")
    if status == 429:
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        raise LLMRateLimitError("provider rate limit", retry_after=retry_after)
    if status >= 500:
        raise LLMServerError(f"provider error ({status})")
    raise LLMBadRequestError(f"provider rejected the request ({status})")


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_tokens_param: str = "max_tokens",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.default_model = model
        self._api_key = api_key
        self._max_tokens_param = max_tokens_param
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self.default_model)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def healthcheck(self) -> bool:
        return self.configured

    async def generate(self, request: LLMRequest) -> LLMResult:
        if not self.configured:
            raise LLMConfigError("OPENAI_API_KEY and OPENAI_MODEL must be set.")

        model = request.model or self.default_model
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(request)},
            ],
            "temperature": request.temperature,
            self._max_tokens_param: request.max_tokens,
        }
        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("provider timed out") from exc
        except httpx.TransportError as exc:
            raise LLMServerError("could not reach the provider") from exc

        _raise_for_status(response)

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMContentError("provider returned an unexpected body") from exc
        if not isinstance(text, str) or not text.strip():
            raise LLMContentError("provider returned an empty completion")

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return LLMResult(
            text=text.strip(),
            provider=self.name,
            model=data.get("model") or model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
