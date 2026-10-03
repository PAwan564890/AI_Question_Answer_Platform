"""Health, readiness, metrics, and cross-cutting middleware behaviour."""

from prometheus_client import REGISTRY
from qdrant_client.http.exceptions import ResponseHandlingException


def sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_health_ok(harness):
    response = await harness.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok", "llm": "mock", "embeddings": "hash"},
        "version": "1.0.0",
    }
    assert (await harness.client.get("/health/ready")).status_code == 200
    assert (await harness.client.get("/health/live")).json() == {"status": "ok"}


async def test_redis_down_is_degraded_but_still_ready_and_live(harness):
    harness.redis_server.connected = False
    health = await harness.client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "degraded" and health.json()["checks"]["redis"] == "fail"

    ready = await harness.client.get("/health/ready")
    # Chat fails open without Redis, so the replica must stay in the load balancer.
    assert ready.status_code == 200 and ready.json()["checks"] == {
        "database": "ok",
        "redis": "fail",
    }
    assert (await harness.client.get("/health/live")).status_code == 200
    assert sample("dependency_up", dependency="redis") == 0.0


async def test_database_down_is_unhealthy_and_not_ready_but_live(harness, monkeypatch):
    async def down(*args, **kwargs):
        raise ResponseHandlingException("connection refused")

    monkeypatch.setattr(harness.app.state.container.qdrant, "get_collections", down)
    health = await harness.client.get("/health")
    assert health.status_code == 503 and health.json()["status"] == "unhealthy"
    assert "connection refused" not in health.text
    assert (await harness.client.get("/health/ready")).status_code == 503
    assert (await harness.client.get("/health/live")).status_code == 200


async def test_database_error_in_a_route_is_a_clean_503(harness, monkeypatch):
    headers = await harness.auth("admin1")

    async def down(*args, **kwargs):
        raise ResponseHandlingException("connection refused to 10.0.0.5:6333")

    monkeypatch.setattr(harness.app.state.container.qdrant, "scroll", down)
    response = await harness.client.get("/admin/users", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "10.0.0.5" not in response.text


async def test_unexpected_exception_is_a_500_without_internals(harness, monkeypatch):
    headers = await harness.auth("alice")

    async def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(harness.app.state.container.chat_service, "ask", boom)
    response = await harness.client.post("/chat", json={"question": "hi"}, headers=headers)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in response.text
    assert response.headers["x-request-id"] == response.json()["error"]["request_id"]


async def test_metrics_require_admin_and_expose_expected_series(harness):
    assert (await harness.client.get("/metrics")).status_code == 401
    admin = await harness.auth("admin1")
    await harness.client.post("/chat", json={"question": "metrics?"}, headers=admin)
    response = await harness.client.get("/metrics", headers=admin)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    for name in (
        "http_requests_total",
        "http_request_duration_seconds_bucket",
        "http_errors_total",
        "llm_requests_total",
        "llm_request_duration_seconds_bucket",
        "llm_tokens_total",
        "llm_circuit_state",
        "cache_requests_total",
        "rag_retrievals_total",
        "dependency_up",
    ):
        assert name in response.text, name


async def test_metrics_scrape_token(build_harness):
    harness = await build_harness(metrics_scrape_token="scrape-token-for-prometheus")
    ok = await harness.client.get(
        "/metrics", headers={"Authorization": "Bearer scrape-token-for-prometheus"}
    )
    assert ok.status_code == 200
    bad = await harness.client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
    assert bad.status_code == 401


async def test_counters_increment_with_low_cardinality_labels(harness):
    headers = await harness.auth("alice")
    http_before = sample("http_requests_total", method="POST", route="/chat", status="200")
    llm_before = sample("llm_requests_total", provider="mock", outcome="success")
    miss_before = sample("cache_requests_total", result="miss")
    hit_before = sample("cache_requests_total", result="hit")

    for _ in range(2):
        await harness.client.post("/chat", json={"question": "count me"}, headers=headers)

    assert (
        sample("http_requests_total", method="POST", route="/chat", status="200") == http_before + 2
    )
    assert sample("llm_requests_total", provider="mock", outcome="success") == llm_before + 1
    assert sample("cache_requests_total", result="miss") == miss_before + 1
    assert sample("cache_requests_total", result="hit") == hit_before + 1


async def test_route_label_is_the_template_not_the_raw_url(harness):
    admin = await harness.auth("admin1")
    await harness.client.patch(
        "/admin/users/some-unique-id-123", json={"role": "USER"}, headers=admin
    )
    await harness.client.get("/no/such/path/987654")
    text = (await harness.client.get("/metrics", headers=admin)).text
    assert 'route="/admin/users/{user_id}"' in text
    assert "some-unique-id-123" not in text and "987654" not in text
    assert 'route="unmatched"' in text


async def test_rate_limit_events_metric(build_harness):
    from app.models import Role

    harness = await build_harness(chat_rate_limit=1)
    await harness.add_user("alice", Role.USER)
    headers = await harness.auth("alice")
    before = sample("rate_limit_events_total", scope="chat")
    await harness.client.post("/chat", json={"question": "one"}, headers=headers)
    await harness.client.post("/chat", json={"question": "two"}, headers=headers)
    assert sample("rate_limit_events_total", scope="chat") == before + 1


async def test_request_id_propagation_and_security_headers(harness):
    response = await harness.client.get("/health/live", headers={"X-Request-ID": "my-trace-id-123"})
    assert response.headers["x-request-id"] == "my-trace-id-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-served-by"]

    # A hostile id (log injection attempt) is replaced by a generated one.
    replaced = await harness.client.get(
        "/health/live", headers={"X-Request-ID": "bad id\twith junk"}
    )
    assert replaced.headers["x-request-id"] != "bad id\twith junk"


async def test_oversized_body_is_413(build_harness):
    harness = await build_harness(max_body_bytes=1024)
    response = await harness.client.post(
        "/auth/login", json={"username": "alice", "password": "x" * 5000}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_unknown_route_and_wrong_method_use_envelope(harness):
    missing = await harness.client.get("/nope")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"
    wrong = await harness.client.get("/auth/login")
    assert wrong.status_code == 405 and wrong.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
