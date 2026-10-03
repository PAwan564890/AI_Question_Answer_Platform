"""Embedding providers: turn text into the vectors stored in Qdrant.

Two implementations share one interface:

* ``HashEmbedder`` (default): a deterministic "hashing trick" bag-of-words
  vector. It needs no model download, no API key and no network, so the RAG
  pipeline runs anywhere and tests are reproducible. It matches on shared
  *words*, not on meaning: "car" and "automobile" are unrelated to it.
* ``OpenAICompatibleEmbedder``: calls a real embedding model through the
  OpenAI-style ``/embeddings`` endpoint for true semantic search.

Vectors produced by different embedders are not comparable, so switching
provider requires re-ingesting the documents.
"""

import hashlib
import math
import re
from collections import Counter
from typing import Protocol

import httpx

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a about all also am an and any are as at be been but by can could did do does for from "
    "had has have he her his how i if in into is it its just me more most my no not of on or "
    "our please she should so some such tell than that the their them then there these they "
    "this those to us very was we were what when where which who why will with would you "
    "your".split()
)


class EmbeddingError(Exception):
    """Embedding failed; RAG degrades to answering without context."""


class Embedder(Protocol):
    name: str
    dim: int

    @property
    def configured(self) -> bool: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int = 2048) -> None:
        self.dim = dim

    @property
    def configured(self) -> bool:
        return True

    def embed_one(self, text: str) -> list[float]:
        # Each distinct word is hashed to one of `dim` positions. The weight is
        # 1 + log(count), so a word repeated ten times does not count ten times.
        vector = [0.0] * self.dim
        for word, count in Counter(tokenize(text)).items():
            digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0  # signed hashing reduces collision bias
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector  # no usable tokens; callers skip all-zero vectors
        return [v / norm for v in vector]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]


class OpenAICompatibleEmbedder:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.dim = dim
        self._api_key = api_key
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport
        )

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._model)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.configured:
            raise EmbeddingError("EMBEDDING_API_KEY and EMBEDDING_MODEL must be set.")
        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self._model, "input": texts},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            rows = sorted(response.json()["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in rows]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise EmbeddingError(f"embedding request failed: {type(exc).__name__}") from exc
        if len(vectors) != len(texts) or any(len(v) != self.dim for v in vectors):
            raise EmbeddingError(
                f"embedding size mismatch: expected {len(texts)} vectors of {self.dim} dimensions"
            )
        return vectors
