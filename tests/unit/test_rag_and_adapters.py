"""Chunking, embeddings and the OpenAI-compatible adapters (HTTP is stubbed)."""

import math

import httpx
import pytest

from app.services.llm.base import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigError,
    LLMContentError,
    LLMRateLimitError,
    LLMRequest,
    LLMServerError,
    LLMTimeoutError,
    build_user_message,
)
from app.services.llm.openai_compat import OpenAICompatibleProvider
from app.services.rag.embeddings import EmbeddingError, HashEmbedder, OpenAICompatibleEmbedder
from app.services.rag.knowledge_base import chunk_text


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_chunking_packs_paragraphs_and_respects_size():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 20 for i in range(10))
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    assert "Paragraph 0" in chunks[0] and "Paragraph 9" in chunks[-1]


def test_chunking_splits_long_paragraph_with_overlap():
    text = "".join(str(i % 10) for i in range(1000))
    chunks = chunk_text(text, size=400, overlap=100)
    assert all(len(c) <= 400 for c in chunks)
    assert chunks[0][-100:] == chunks[1][:100]  # consecutive windows overlap
    assert chunk_text("   \n\n  ", 400, 100) == []


def test_hash_embedder_is_deterministic_normalised_and_lexical():
    embedder = HashEmbedder(dim=256)
    redis_doc = embedder.embed_one("Redis is an in-memory data store used for caching.")
    assert redis_doc == embedder.embed_one("Redis is an in-memory data store used for caching.")
    assert len(redis_doc) == 256
    assert math.isclose(math.sqrt(sum(v * v for v in redis_doc)), 1.0, rel_tol=1e-9)

    query = embedder.embed_one("What is Redis caching?")
    unrelated = embedder.embed_one("Bananas grow in tropical climates.")
    assert cosine(query, redis_doc) > cosine(query, unrelated)
    assert not any(embedder.embed_one("the of and"))  # only stop-words => zero vector


def test_prompt_keeps_user_text_inside_delimiters():
    message = build_user_message(LLMRequest(question="Q?", context=("first", "second")))
    assert "<context>\n[1] first\n[2] second\n</context>" in message
    assert message.endswith("<question>\nQ?\n</question>")
    assert "<context>" not in build_user_message(LLMRequest(question="Q?"))


def make_provider(handler, **kwargs) -> OpenAICompatibleProvider:
    options = {
        "base_url": "https://llm.example/v1",
        "api_key": "test-key",
        "model": "test-model",
        "timeout_seconds": 1,
    }
    return OpenAICompatibleProvider(**{**options, **kwargs}, transport=httpx.MockTransport(handler))


async def test_openai_adapter_success_and_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "test-model-2025",
                "choices": [{"message": {"content": " Redis is a data store. "}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
            },
        )

    provider = make_provider(handler)
    result = await provider.generate(LLMRequest(question="What is Redis?", max_tokens=99))
    assert result.text == "Redis is a data store."
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (12, 6, 18)
    assert result.model == "test-model-2025" and result.provider == "openai_compatible"
    assert seen["url"] == "https://llm.example/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["messages"][0]["role"] == "system"
    assert seen["body"]["max_tokens"] == 99
    await provider.aclose()


async def test_openai_adapter_usage_is_null_when_not_reported():
    provider = make_provider(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
    )
    result = await provider.generate(LLMRequest(question="q"))
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (None,) * 3


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(401, json={"error": "bad key"}), LLMAuthError),
        (httpx.Response(403), LLMAuthError),
        (httpx.Response(429, headers={"retry-after": "7"}), LLMRateLimitError),
        (httpx.Response(500), LLMServerError),
        (httpx.Response(503), LLMServerError),
        (httpx.Response(400, json={"error": "context too long"}), LLMBadRequestError),
        (httpx.Response(200, json={"choices": []}), LLMContentError),
        (httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}), LLMContentError),
        (httpx.Response(200, text="not json"), LLMContentError),
    ],
)
async def test_openai_adapter_error_classification(response, error):
    provider = make_provider(lambda r: response)
    with pytest.raises(error) as excinfo:
        await provider.generate(LLMRequest(question="q"))
    if error is LLMRateLimitError:
        assert excinfo.value.retry_after == 7.0


async def test_openai_adapter_network_failures():
    def timeout(request):
        raise httpx.ReadTimeout("slow")

    def refused(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMTimeoutError):
        await make_provider(timeout).generate(LLMRequest(question="q"))
    with pytest.raises(LLMServerError):
        await make_provider(refused).generate(LLMRequest(question="q"))


async def test_openai_adapter_without_key_is_unconfigured():
    provider = make_provider(lambda r: httpx.Response(200), api_key="")
    assert not provider.configured
    with pytest.raises(LLMConfigError):
        await provider.generate(LLMRequest(question="q"))


async def test_openai_embedder_success_and_failures():
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    def make(handler, **kwargs):
        options = {"base_url": "https://emb.example/v1", "api_key": "k", "model": "m", "dim": 2}
        return OpenAICompatibleEmbedder(
            **{**options, **kwargs}, transport=httpx.MockTransport(handler)
        )

    assert await make(ok).embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]  # re-ordered by index
    with pytest.raises(EmbeddingError):
        await make(ok, dim=3).embed(["a", "b"])  # dimension mismatch
    with pytest.raises(EmbeddingError):
        await make(lambda r: httpx.Response(500)).embed(["a"])
    with pytest.raises(EmbeddingError):
        await make(ok, api_key="").embed(["a"])
