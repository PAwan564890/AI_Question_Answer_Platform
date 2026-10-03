"""Shared fixtures.

The default test run needs no Docker and no network: Qdrant runs in the
client's in-memory mode, Redis is fakeredis, and the LLM is the mock provider.
"""

from dataclasses import dataclass

import fakeredis
import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.core.security import hash_password
from app.database.bootstrap import ensure_collections
from app.main import create_app
from app.models import Role
from app.repositories.users import UserRepository
from app.services.llm.mock import MockProvider

TEST_PASSWORD = "Correct-Horse-42"
TEST_SECRET = "unit-test-secret-that-is-long-enough-0123456789"


def make_settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "jwt_secret": TEST_SECRET,
        "log_level": "WARNING",
        "llm_provider": "mock",
        "llm_allowed_models": "mock-1,mock-2",
        "llm_timeout_seconds": 0.05,
        "llm_overall_deadline_seconds": 2.0,
        "llm_backoff_base_seconds": 0.001,
        "llm_backoff_max_seconds": 0.002,
        "llm_queue_wait_seconds": 0.05,
        "chat_rate_limit": 50,
        "login_max_attempts": 3,
        "breaker_failure_threshold": 5,
        "embedding_dim": 2048,
    }
    values.update(overrides)
    # _env_file=None: tests must not pick up a developer's local .env
    return Settings(_env_file=None, **values)


@dataclass
class Harness:
    """Everything a test may want to poke at."""

    client: httpx.AsyncClient
    app: object
    primary: MockProvider
    fallback: MockProvider | None
    redis_server: fakeredis.FakeServer
    users: UserRepository
    hashed_password: str

    async def add_user(self, username: str, role: Role, *, active: bool = True) -> str:
        user = await self.users.create(username, self.hashed_password, role)
        if not active:
            await self.users.update_fields(user.id, {"is_active": False})
        return user.id

    async def token(self, username: str) -> str:
        response = await self.client.post(
            "/auth/login", json={"username": username, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    async def auth(self, username: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.token(username)}"}


@pytest.fixture(scope="session")
def hashed_password() -> str:
    return hash_password(TEST_PASSWORD)  # Argon2 is slow on purpose: hash once per run


@pytest.fixture
async def build_harness(hashed_password):
    """Factory fixture so a test can choose settings or add a fallback provider."""
    created: list[Harness] = []

    async def _build(*, with_fallback: bool = False, primary=None, **setting_overrides) -> Harness:
        settings = make_settings(**setting_overrides)
        qdrant = AsyncQdrantClient(location=":memory:")
        await ensure_collections(qdrant, settings.embedding_dim)
        server = fakeredis.FakeServer()
        redis = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
        primary = primary or MockProvider()
        fallback = None
        if with_fallback:
            fallback = MockProvider(default_model="mock-fallback")
            fallback.name = "mock_fallback"
        app = create_app(settings, qdrant=qdrant, redis=redis, primary=primary, fallback=fallback)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )
        harness = Harness(
            client, app, primary, fallback, server, UserRepository(qdrant), hashed_password
        )
        created.append(harness)
        return harness

    yield _build
    for harness in created:
        await harness.client.aclose()


@pytest.fixture
async def harness(build_harness) -> Harness:
    h = await build_harness()
    await h.add_user("alice", Role.USER)
    await h.add_user("admin1", Role.ADMIN)
    await h.add_user("reader", Role.READ_ONLY)
    return h
