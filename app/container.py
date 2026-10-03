"""Wires the application's long-lived objects together (one set per process).

Everything stateful (Qdrant client, Redis client, LLM gateway) is created
here once and shared by all requests. Tests pass in fakes for the external
pieces; production passes nothing and gets the real ones.
"""

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.core.config import Settings
from app.database.client import create_qdrant_client
from app.repositories.chats import AuditRepository, ChatRepository
from app.repositories.documents import DocumentRepository
from app.repositories.users import UserRepository
from app.services.auth_service import AuthService, UserService
from app.services.cache import ResponseCache
from app.services.chat_service import ChatService
from app.services.llm.base import LLMProvider
from app.services.llm.gateway import LLMGateway
from app.services.llm.mock import MockProvider
from app.services.llm.openai_compat import OpenAICompatibleProvider
from app.services.rag.embeddings import Embedder, HashEmbedder, OpenAICompatibleEmbedder
from app.services.rag.knowledge_base import KnowledgeBase
from app.services.rate_limiter import ChatRateLimiter, LoginThrottle


@dataclass(slots=True)
class Container:
    settings: Settings
    qdrant: AsyncQdrantClient
    redis: Redis
    users: UserRepository
    chats: ChatRepository
    audit: AuditRepository
    embedder: Embedder
    knowledge_base: KnowledgeBase
    gateway: LLMGateway
    auth_service: AuthService
    user_service: UserService
    chat_service: ChatService

    async def aclose(self) -> None:
        for resource in (self.gateway.primary, self.gateway.fallback, self.embedder):
            if resource is not None and hasattr(resource, "aclose"):
                await resource.aclose()
        await self.redis.aclose()
        await self.qdrant.close()


def build_provider(name: str, settings: Settings) -> LLMProvider:
    if name == "mock":
        return MockProvider(latency_seconds=settings.mock_latency_seconds)
    return OpenAICompatibleProvider(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens_param=settings.openai_max_tokens_param,
    )


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "hash":
        return HashEmbedder(settings.embedding_dim)
    return OpenAICompatibleEmbedder(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        dim=settings.embedding_dim,
    )


def build_container(
    settings: Settings,
    *,
    qdrant: AsyncQdrantClient | None = None,
    redis: Redis | None = None,
    primary: LLMProvider | None = None,
    fallback: LLMProvider | None = None,
    embedder: Embedder | None = None,
) -> Container:
    qdrant = qdrant or create_qdrant_client(settings)
    redis = redis or Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2,
    )
    primary = primary or build_provider(settings.llm_provider, settings)
    if fallback is None and settings.llm_fallback_provider:
        fallback = build_provider(settings.llm_fallback_provider, settings)
    embedder = embedder or build_embedder(settings)

    users = UserRepository(qdrant)
    chats = ChatRepository(qdrant)
    audit = AuditRepository(qdrant)
    knowledge_base = KnowledgeBase(settings, embedder, DocumentRepository(qdrant), redis, audit)
    gateway = LLMGateway(
        primary,
        fallback,
        timeout_seconds=settings.llm_timeout_seconds,
        overall_deadline_seconds=settings.llm_overall_deadline_seconds,
        max_retries=settings.llm_max_retries,
        backoff_base_seconds=settings.llm_backoff_base_seconds,
        backoff_max_seconds=settings.llm_backoff_max_seconds,
        max_concurrency=settings.llm_max_concurrency,
        queue_wait_seconds=settings.llm_queue_wait_seconds,
        breaker_failure_threshold=settings.breaker_failure_threshold,
        breaker_reset_seconds=settings.breaker_reset_seconds,
    )
    return Container(
        settings=settings,
        qdrant=qdrant,
        redis=redis,
        users=users,
        chats=chats,
        audit=audit,
        embedder=embedder,
        knowledge_base=knowledge_base,
        gateway=gateway,
        auth_service=AuthService(
            settings,
            users,
            LoginThrottle(redis, settings.login_max_attempts, settings.login_lockout_seconds),
        ),
        user_service=UserService(users, audit, redis),
        chat_service=ChatService(
            settings,
            gateway,
            ResponseCache(redis, settings.cache_ttl_seconds, settings.cache_enabled),
            ChatRateLimiter(redis, settings.chat_rate_limit, settings.chat_rate_window_seconds),
            knowledge_base,
            chats,
        ),
    )
