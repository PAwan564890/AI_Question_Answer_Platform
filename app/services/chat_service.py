"""/chat orchestration: rate limit -> cache -> retrieve -> LLM -> persist.

How this works:

1. Rate limit first, so every request (even one that will be a cache hit)
   counts against the user's quota.
2. Cache lookup. A hit skips retrieval and the LLM entirely.
3. Retrieval (RAG): the question is embedded and the closest knowledge-base
   chunks are fetched from Qdrant. A retrieval failure degrades to answering
   without context rather than failing the request.
4. The LLM gateway is called. No database call is in flight while we wait for
   the model, so a slow provider cannot pin database connections.
5. The outcome (success or failure) is written to Qdrant, and a successful
   answer is cached.
"""

import logging
import time
import uuid
from datetime import UTC, datetime

from qdrant_client.http.exceptions import ApiException
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import AppError, InvalidRequestError
from app.models import ChatRecord, RetrievedChunk, User
from app.monitoring import metrics
from app.repositories.chats import ChatRepository
from app.schemas.chat import ChatRequest, ChatResponse, Source, Usage
from app.services.cache import ResponseCache, build_cache_key
from app.services.llm.base import (
    PROMPT_VERSION,
    LLMAuthError,
    LLMBadRequestError,
    LLMCircuitOpenError,
    LLMConfigError,
    LLMContentError,
    LLMError,
    LLMOverloadedError,
    LLMRateLimitError,
    LLMRequest,
    LLMServerError,
    LLMTimeoutError,
)
from app.services.llm.gateway import LLMGateway
from app.services.rag.embeddings import EmbeddingError
from app.services.rag.knowledge_base import KnowledgeBase
from app.services.rate_limiter import ChatRateLimiter

logger = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 0.2

# LLM failure -> (HTTP status, public error code, public message).
# The public message is generic on purpose: provider details stay in the logs.
_LLM_ERROR_MAP: dict[type[LLMError], tuple[int, str, str]] = {
    LLMTimeoutError: (504, "LLM_TIMEOUT", "The language model did not respond in time."),
    LLMContentError: (502, "LLM_BAD_RESPONSE", "The language model returned an unusable response."),
    LLMBadRequestError: (502, "LLM_BAD_REQUEST", "The language model rejected the request."),
    LLMRateLimitError: (503, "LLM_RATE_LIMITED", "The language model is busy. Try again shortly."),
    LLMServerError: (503, "LLM_UNAVAILABLE", "The language model is temporarily unavailable."),
    LLMAuthError: (503, "LLM_UNAVAILABLE", "The language model is temporarily unavailable."),
    LLMConfigError: (503, "LLM_NOT_CONFIGURED", "No language model provider is configured."),
    LLMCircuitOpenError: (
        503,
        "LLM_CIRCUIT_OPEN",
        "The language model is temporarily unavailable.",
    ),
    LLMOverloadedError: (503, "LLM_OVERLOADED", "The service is at capacity. Try again shortly."),
}


def llm_error_to_app_error(error: LLMError) -> AppError:
    status, code, message = _LLM_ERROR_MAP.get(
        type(error), (503, "LLM_UNAVAILABLE", "The language model is temporarily unavailable.")
    )
    headers = {}
    if isinstance(error, LLMRateLimitError | LLMOverloadedError | LLMCircuitOpenError):
        headers["Retry-After"] = str(max(1, int(error.retry_after or 5)))
    return AppError(message, code=code, status_code=status, headers=headers)


class ChatService:
    def __init__(
        self,
        settings: Settings,
        gateway: LLMGateway,
        cache: ResponseCache,
        limiter: ChatRateLimiter,
        knowledge_base: KnowledgeBase,
        chats: ChatRepository,
    ) -> None:
        self._settings = settings
        self._gateway = gateway
        self._cache = cache
        self._limiter = limiter
        self._kb = knowledge_base
        self._chats = chats

    async def ask(self, user: User, payload: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        primary = self._gateway.primary
        model = payload.model or primary.default_model
        if model not in self._settings.allowed_models | {primary.default_model}:
            raise InvalidRequestError(
                "The requested model is not allowed.", code="MODEL_NOT_ALLOWED"
            )
        temperature = DEFAULT_TEMPERATURE if payload.temperature is None else payload.temperature
        use_rag = self._settings.rag_enabled and payload.use_rag

        await self._limiter.check(user.id)

        cache_key = await self._cache_key(user, payload, model, temperature, use_rag)
        if cache_key and (hit := await self._cache.get(cache_key)):
            # No provider call happened, so no tokens were used by this request.
            response = ChatResponse(
                id=str(uuid.uuid4()),
                answer=hit["answer"],
                provider=hit["provider"],
                model=hit["model"],
                cached=True,
                usage=Usage(),
                latency_ms=_elapsed_ms(started),
                sources=hit["sources"],
            )
            await self._persist(user, payload, response, status="ok", error_code=None)
            return response

        chunks = await self._retrieve(payload.question) if use_rag else []
        request = LLMRequest(
            question=payload.question,
            context=tuple(c.text for c in chunks),
            model=payload.model,
            temperature=temperature,
            max_tokens=self._settings.llm_max_output_tokens,
        )
        try:
            outcome = await self._gateway.generate(request)
        except LLMError as exc:
            app_error = llm_error_to_app_error(exc)
            logger.error(
                "chat_llm_failed",
                extra={"user_id": user.id, "error_code": exc.code, "retries": exc.retries_used},
            )
            failed = ChatResponse(
                id=str(uuid.uuid4()),
                answer="",
                provider="",
                model=model,
                cached=False,
                usage=Usage(),
                latency_ms=_elapsed_ms(started),
                retries=exc.retries_used,
            )
            await self._persist(user, payload, failed, status="error", error_code=app_error.code)
            raise app_error from exc

        result = outcome.result
        response = ChatResponse(
            id=str(uuid.uuid4()),
            answer=result.text,
            provider=result.provider,
            model=result.model,
            cached=False,
            usage=Usage(
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
            ),
            latency_ms=_elapsed_ms(started),
            retries=outcome.retries,
            fallback_used=outcome.fallback_used,
            sources=[
                Source(doc_id=c.doc_id, title=c.title, chunk_index=c.chunk_index, score=c.score)
                for c in chunks
            ],
        )
        await self._persist(user, payload, response, status="ok", error_code=None)
        # A fallback answer is not cached: once the primary recovers, users
        # should get the primary's answer again.
        if cache_key and not outcome.fallback_used:
            await self._cache.set(
                cache_key,
                {
                    "answer": response.answer,
                    "provider": response.provider,
                    "model": response.model,
                    "sources": [s.model_dump() for s in response.sources],
                },
            )
        return response

    async def _cache_key(
        self, user: User, payload: ChatRequest, model: str, temperature: float, use_rag: bool
    ) -> str | None:
        if not self._settings.cache_enabled:
            return None
        try:
            kb_version = await self._kb.version() if use_rag else "-"
        except RedisError:
            return None  # Redis is down: behave as if there were no cache
        return build_cache_key(
            user_id=user.id,
            question=payload.question,
            provider=self._gateway.primary.name,
            model=model,
            temperature=temperature,
            prompt_version=PROMPT_VERSION,
            use_rag=use_rag,
            kb_version=kb_version,
        )

    async def _retrieve(self, question: str) -> list[RetrievedChunk]:
        try:
            chunks = await self._kb.search(question)
        except (EmbeddingError, ApiException) as exc:
            metrics.RAG_RETRIEVALS.labels(outcome="error").inc()
            logger.error("rag_retrieval_failed", extra={"reason": type(exc).__name__})
            return []
        metrics.RAG_RETRIEVALS.labels(outcome="hit" if chunks else "empty").inc()
        return chunks

    async def _persist(
        self,
        user: User,
        payload: ChatRequest,
        response: ChatResponse,
        *,
        status: str,
        error_code: str | None,
    ) -> None:
        store_text = self._settings.store_chat_content
        record = ChatRecord(
            id=response.id,
            user_id=user.id,
            question=payload.question if store_text else None,
            answer=(response.answer or None) if store_text else None,
            provider=response.provider or None,
            model=response.model,
            cached=response.cached,
            status=status,
            error_code=error_code,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            retries=response.retries,
            fallback_used=response.fallback_used,
            created_at=datetime.now(UTC),
            sources=[s.model_dump() for s in response.sources],
        )
        try:
            await self._chats.add(record)
        except ApiException:
            # The user already waited for (and we already paid for) the answer:
            # return it, and surface the lost record through logs and a metric.
            metrics.CHAT_PERSIST_FAILURES.inc()
            logger.exception("chat_persist_failed", extra={"user_id": user.id})


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
