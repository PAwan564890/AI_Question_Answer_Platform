"""Integration tests against REAL Redis and Qdrant servers.

    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d qdrant redis
    RUN_INTEGRATION=1 pytest -m integration

They are skipped by default so the normal suite needs no Docker. They prove the
things fakes cannot: the bootstrap works on a real Qdrant server (payload
indexes, ordered scroll), and the rate limiter is atomic on a real Redis.
"""

import asyncio
import os
import uuid

import pytest
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.database.bootstrap import ensure_collections
from app.models import Role
from app.repositories.documents import DocumentRepository
from app.repositories.users import UserRepository
from app.services.rag.embeddings import HashEmbedder
from app.services.rate_limiter import RateLimiter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1"),
]

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def test_bootstrap_is_idempotent_and_users_roundtrip():
    client = AsyncQdrantClient(url=QDRANT_URL)
    try:
        await ensure_collections(client, 2048)
        await ensure_collections(client, 2048)  # second run must be a no-op
        users = UserRepository(client)
        name = f"it_{uuid.uuid4().hex[:10]}"
        created = await users.create(name, "not-a-real-hash", Role.READ_ONLY)
        loaded = await users.get_by_username(name.upper())
        assert loaded is not None and loaded.id == created.id and loaded.role is Role.READ_ONLY
        assert name in [u.username for u in await users.list(limit=100, offset=0)]
    finally:
        await client.close()


async def test_vector_search_on_real_qdrant():
    client = AsyncQdrantClient(url=QDRANT_URL)
    try:
        await ensure_collections(client, 2048)
        embedder, documents = HashEmbedder(2048), DocumentRepository(client)
        marker = f"quokka{uuid.uuid4().hex[:8]}"
        chunks = [f"The {marker} service listens on port 9099.", "Bananas are yellow."]
        info = await documents.add(
            title="integration",
            source=None,
            created_by="it",
            embedding_model="hash",
            chunks=chunks,
            vectors=await embedder.embed(chunks),
        )
        try:
            query = embedder.embed_one(f"{marker} port")
            hits = await documents.search(query, top_k=1, score_threshold=0.1)
            assert hits and marker in hits[0].text
            assert info.doc_id in [d.doc_id for d in await documents.list(100, 0)]
        finally:
            assert await documents.delete(info.doc_id)
    finally:
        await client.close()


async def test_rate_limiter_is_atomic_under_concurrency_on_real_redis():
    """50 concurrent hits from two clients ("replicas"): exactly `limit` are allowed."""
    replica_a = Redis.from_url(REDIS_URL, decode_responses=True)
    replica_b = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        identity = f"it-{uuid.uuid4().hex}"
        limiters = [RateLimiter(replica_a), RateLimiter(replica_b)]
        results = await asyncio.gather(
            *(limiters[i % 2].hit("it", identity, limit=20, window=300) for i in range(50))
        )
        assert sum(r.allowed for r in results) == 20
    finally:
        await replica_a.aclose()
        await replica_b.aclose()
