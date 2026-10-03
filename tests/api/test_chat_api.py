"""/chat end to end: resilience, rate limiting, caching, RAG, persistence."""

import pytest
from qdrant_client.http.exceptions import ResponseHandlingException

from app.models import Role

REDIS_DOC = {
    "title": "Redis notes",
    "text": (
        "Redis is an in-memory data store used for caching and rate limiting.\n\n"
        "Qdrant is a vector database that stores embeddings for similarity search."
    ),
}


async def ask(harness, username="alice", **body):
    body.setdefault("question", "What is Redis?")
    return await harness.client.post("/chat", json=body, headers=await harness.auth(username))


async def test_chat_success_shape_and_persistence(harness):
    response = await ask(harness)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("[mock]")
    assert body["provider"] == "mock" and body["model"] == "mock-1"
    assert body["cached"] is False and body["retries"] == 0 and body["fallback_used"] is False
    assert body["usage"]["total_tokens"] == (
        body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]
    )
    assert body["latency_ms"] >= 0

    history = await harness.client.get("/chat/history", headers=await harness.auth("alice"))
    (row,) = history.json()
    assert row["id"] == body["id"] and row["status"] == "ok" and row["sources"] == []
    assert row["question"] == "What is Redis?" and row["usage"] == body["usage"]


@pytest.mark.parametrize(
    "body",
    [{}, {"question": "   "}, {"question": "x" * 4001}, {"question": "hi", "temperature": 2}],
)
async def test_chat_invalid_body_is_422(harness, body):
    response = await harness.client.post("/chat", json=body, headers=await harness.auth("alice"))
    assert response.status_code == 422
    assert harness.primary.calls == 0


async def test_model_allowlist(harness):
    assert (await ask(harness, model="mock-2")).json()["model"] == "mock-2"
    rejected = await ask(harness, model="some-expensive-model")
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "MODEL_NOT_ALLOWED"


async def test_provider_timeout_returns_504_after_bounded_retries(harness):
    harness.primary.script("timeout", "timeout", "timeout", "ok")
    response = await ask(harness)
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "LLM_TIMEOUT"
    assert harness.primary.calls == 3  # 1 + LLM_MAX_RETRIES(2), never the 4th

    history = await harness.client.get("/chat/history", headers=await harness.auth("alice"))
    row = history.json()[0]
    assert row["status"] == "error" and row["error_code"] == "LLM_TIMEOUT" and row["retries"] == 2


async def test_provider_5xx_retries_then_succeeds(harness):
    harness.primary.script("server_error", "ok")
    response = await ask(harness)
    assert response.status_code == 200 and response.json()["retries"] == 1


async def test_provider_5xx_without_fallback_is_503_with_no_internals(harness):
    harness.primary.script(*["server_error"] * 3)
    response = await ask(harness)
    assert response.status_code == 503
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message", "request_id"}
    for leaked in ("mock 500", "Traceback", "LLMServerError", "qdrant", "redis"):
        assert leaked not in response.text


async def test_provider_5xx_uses_fallback_when_configured(build_harness):
    harness = await build_harness(with_fallback=True)
    await harness.add_user("alice", Role.USER)
    harness.primary.script(*["server_error"] * 3)
    response = await ask(harness)
    assert response.status_code == 200
    body = response.json()
    assert body["fallback_used"] is True and body["provider"] == "mock_fallback"
    assert body["retries"] == 2

    # A fallback answer is not cached: the next call goes back to the primary.
    again = (await ask(harness)).json()
    assert again["cached"] is False and again["provider"] == "mock"


async def test_provider_429_honours_retry_after(harness):
    harness.primary.retry_after = 0.01
    harness.primary.script("rate_limit", "ok")
    response = await ask(harness)
    assert response.status_code == 200 and response.json()["retries"] == 1


async def test_provider_429_exhausted_is_503_with_retry_after(harness):
    harness.primary.retry_after = 0.01
    harness.primary.script(*["rate_limit"] * 3)
    response = await ask(harness)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_RATE_LIMITED"
    assert "retry-after" in response.headers


async def test_provider_auth_error_is_not_retried(harness):
    harness.primary.script("auth_error", "ok")
    response = await ask(harness)
    assert response.status_code == 503 and harness.primary.calls == 1
    assert "auth" not in response.text.lower()  # an operator problem is not shown to users


async def test_malformed_provider_output_is_502(harness):
    harness.primary.script("empty", "empty")
    response = await ask(harness)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_BAD_RESPONSE"


async def test_circuit_opens_after_threshold_and_fails_fast(build_harness):
    harness = await build_harness(llm_max_retries=0, breaker_failure_threshold=3)
    await harness.add_user("alice", Role.USER)
    harness.primary.script(*["server_error"] * 3)
    for i in range(3):
        assert (await ask(harness, question=f"q{i}")).status_code == 503
    fast = await ask(harness, question="q-final")
    assert fast.status_code == 503 and fast.json()["error"]["code"] == "LLM_CIRCUIT_OPEN"
    assert harness.primary.calls == 3  # the provider was not called while open


async def test_unconfigured_real_provider_is_a_safe_503(build_harness):
    from app.services.llm.openai_compat import OpenAICompatibleProvider

    unconfigured = OpenAICompatibleProvider(
        base_url="https://llm.example/v1", api_key="", model="", timeout_seconds=1
    )
    harness = await build_harness(primary=unconfigured)
    await harness.add_user("alice", Role.USER)
    response = await ask(harness)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
    health = (await harness.client.get("/health")).json()
    assert health["status"] == "degraded" and health["checks"]["llm"] == "unconfigured"


async def test_chat_rate_limit_returns_429_with_retry_after(build_harness):
    harness = await build_harness(chat_rate_limit=2)
    await harness.add_user("alice", Role.USER)
    await harness.add_user("bob", Role.USER)
    headers = await harness.auth("alice")
    statuses = [
        (await harness.client.post("/chat", json={"question": f"q{i}"}, headers=headers))
        for i in range(3)
    ]
    assert [r.status_code for r in statuses] == [200, 200, 429]
    assert int(statuses[-1].headers["retry-after"]) >= 1
    assert statuses[-1].json()["error"]["code"] == "RATE_LIMITED"
    assert (await ask(harness, username="bob")).status_code == 200  # limits are per user


async def test_cache_hit_skips_provider(harness):
    first = (await ask(harness)).json()
    second = (await ask(harness, question="  what is   REDIS? ")).json()  # normalised to same key
    assert first["cached"] is False and second["cached"] is True
    assert second["answer"] == first["answer"] and second["id"] != first["id"]
    assert harness.primary.calls == 1
    assert second["usage"] == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


async def test_cache_does_not_leak_between_users(harness):
    await harness.add_user("bob", Role.USER)
    assert (await ask(harness, username="alice")).json()["cached"] is False
    assert (await ask(harness, username="bob")).json()["cached"] is False
    assert harness.primary.calls == 2


async def test_errors_are_never_cached(harness):
    harness.primary.script(*["server_error"] * 3)
    assert (await ask(harness)).status_code == 503
    recovered = await ask(harness)
    assert recovered.status_code == 200 and recovered.json()["cached"] is False


async def test_chat_survives_redis_outage(harness):
    headers = await harness.auth("alice")  # log in while Redis is still up
    harness.redis_server.connected = False
    response = await harness.client.post("/chat", json={"question": "hi"}, headers=headers)
    assert response.status_code == 200 and response.json()["cached"] is False
    health = await harness.client.get("/health")
    assert health.status_code == 200 and health.json()["status"] == "degraded"


async def test_rag_answer_uses_retrieved_context_and_cites_sources(harness):
    admin = await harness.auth("admin1")
    before = (await ask(harness)).json()
    assert before["sources"] == []

    created = await harness.client.post("/documents", json=REDIS_DOC, headers=admin)
    assert created.status_code == 201 and created.json()["chunk_count"] == 1

    # Ingesting bumped the knowledge-base version, so the old cached answer is not reused.
    after = (await ask(harness)).json()
    assert after["cached"] is False
    assert "in-memory data store" in after["answer"]
    assert after["sources"][0]["title"] == "Redis notes" and after["sources"][0]["score"] > 0

    without = (await ask(harness, use_rag=False)).json()
    assert without["sources"] == [] and "You asked" in without["answer"]


async def test_documents_search_list_delete(harness):
    admin, reader = await harness.auth("admin1"), await harness.auth("reader")
    doc = (await harness.client.post("/documents", json=REDIS_DOC, headers=admin)).json()

    hits = await harness.client.post(
        "/documents/search", json={"query": "vector database embeddings"}, headers=reader
    )
    assert hits.status_code == 200 and "Qdrant" in hits.json()["results"][0]["text"]

    unrelated = await harness.client.post(
        "/documents/search", json={"query": "bananas tropical fruit"}, headers=reader
    )
    assert unrelated.json()["results"] == []  # below the similarity threshold

    listed = (await harness.client.get("/documents", headers=reader)).json()
    assert [d["doc_id"] for d in listed] == [doc["doc_id"]]

    deleted = await harness.client.delete(f"/documents/{doc['doc_id']}", headers=admin)
    assert deleted.status_code == 204
    assert (await harness.client.get("/documents", headers=reader)).json() == []


async def test_document_too_large_and_empty_are_rejected(build_harness):
    harness = await build_harness(rag_max_document_chars=50)
    await harness.add_user("admin1", Role.ADMIN)
    admin = await harness.auth("admin1")
    too_big = await harness.client.post(
        "/documents", json={"title": "T", "text": "word " * 20}, headers=admin
    )
    assert too_big.status_code == 422
    no_words = await harness.client.post(
        "/documents", json={"title": "T", "text": "the of and"}, headers=admin
    )
    assert no_words.status_code == 422


async def test_store_chat_content_false_keeps_text_out_of_the_database(build_harness):
    harness = await build_harness(store_chat_content=False)
    await harness.add_user("alice", Role.USER)
    assert (await ask(harness)).status_code == 200
    row = (await harness.client.get("/chat/history", headers=await harness.auth("alice"))).json()[0]
    assert row["question"] is None and row["answer"] is None
    assert row["usage"]["total_tokens"] is not None  # usage metadata is still recorded


async def test_history_is_scoped_and_paginated(harness):
    await harness.add_user("bob", Role.USER)
    for i in range(3):
        await ask(harness, question=f"alice question {i}")
    await ask(harness, username="bob", question="bob question")

    alice = await harness.auth("alice")
    mine = (await harness.client.get("/chat/history", headers=alice)).json()
    assert [r["question"] for r in mine] == [f"alice question {i}" for i in (2, 1, 0)]
    page = (await harness.client.get("/chat/history?limit=1&offset=1", headers=alice)).json()
    assert [r["question"] for r in page] == ["alice question 1"]

    everything = await harness.client.get(
        "/chat/history?user_id=all", headers=await harness.auth("admin1")
    )
    assert len(everything.json()) == 4


async def test_answer_is_returned_even_if_persisting_fails(harness, monkeypatch):
    async def broken(*args, **kwargs):
        raise ResponseHandlingException("connection refused")

    monkeypatch.setattr(harness.app.state.container.chats, "add", broken)
    response = await ask(harness)
    assert response.status_code == 200 and response.json()["answer"]
