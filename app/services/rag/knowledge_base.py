"""Knowledge-base service: chunk, embed, store, search (the "R" in RAG).

Ingestion: text -> chunks -> one embedding per chunk -> Qdrant ``documents``.
Retrieval: question -> embedding -> cosine nearest neighbours above a score
threshold -> the chunks handed to the LLM as context.
"""

import logging
import re

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from app.models import DocumentInfo, RetrievedChunk, User
from app.repositories.documents import DocumentRepository
from app.services.rag.embeddings import Embedder, EmbeddingError

logger = logging.getLogger(__name__)

KB_VERSION_KEY = "kb:version"
_PARAGRAPHS = re.compile(r"\n\s*\n")


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into chunks of at most ``size`` characters.

    Paragraphs are packed together until the next one would overflow, which
    keeps related sentences in the same chunk. A single paragraph longer than
    ``size`` is cut into windows that overlap by ``overlap`` characters so a
    sentence straddling a cut is still fully present in one of the chunks.
    """
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in _PARAGRAPHS.split(text)):
        if not paragraph:
            continue
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            step = size - overlap
            chunks.extend(paragraph[i : i + size].strip() for i in range(0, len(paragraph), step))
        elif current and len(current) + 2 + len(paragraph) > size:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


class KnowledgeBase:
    def __init__(
        self, settings: Settings, embedder: Embedder, documents: DocumentRepository, redis: Redis
    ) -> None:
        self._settings = settings
        self._embedder = embedder
        self._documents = documents
        self._redis = redis

    async def version(self) -> str:
        """Counter bumped on every ingest/delete; part of the response-cache key.

        Changing the knowledge base therefore invalidates cached answers that
        were built from the old documents, without scanning or deleting keys.
        """
        return str(await self._redis.get(KB_VERSION_KEY) or "0")

    async def _bump_version(self) -> None:
        try:
            await self._redis.incr(KB_VERSION_KEY)
        except RedisError:
            # Redis down means the cache is unreachable too, so nothing stale is served.
            logger.warning("kb_version_bump_failed")

    async def ingest(
        self, *, title: str, text: str, source: str | None, actor: User
    ) -> DocumentInfo:
        if len(text) > self._settings.rag_max_document_chars:
            raise InvalidRequestError(
                f"Document text exceeds {self._settings.rag_max_document_chars} characters."
            )
        chunks = chunk_text(text, self._settings.rag_chunk_size, self._settings.rag_chunk_overlap)
        try:
            vectors = await self._embedder.embed(chunks)
        except EmbeddingError as exc:
            logger.error("embedding_failed", extra={"reason": str(exc)})
            raise ServiceUnavailableError(
                "The embedding service is unavailable.", code="EMBEDDING_UNAVAILABLE"
            ) from exc
        # A chunk with no indexable words has an all-zero vector, which cosine
        # similarity cannot compare: drop it.
        kept = [(c, v) for c, v in zip(chunks, vectors, strict=True) if any(v)]
        if not kept:
            raise InvalidRequestError("The document contains no indexable text.")
        info = await self._documents.add(
            title=title,
            source=source,
            created_by=actor.id,
            embedding_model=self._embedder.name,
            chunks=[c for c, _ in kept],
            vectors=[v for _, v in kept],
        )
        await self._bump_version()
        logger.info("document_ingested", extra={"doc_id": info.doc_id, "chunks": info.chunk_count})
        return info

    async def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Raises EmbeddingError if the query cannot be embedded."""
        vector = (await self._embedder.embed([query]))[0]
        if not any(vector):
            return []
        return await self._documents.search(
            vector, top_k or self._settings.rag_top_k, self._settings.rag_score_threshold
        )

    async def list(self, limit: int, offset: int) -> list[DocumentInfo]:
        return await self._documents.list(limit, offset)

    async def delete(self, doc_id: str) -> None:
        if not await self._documents.delete(doc_id):
            raise NotFoundError("Document not found.")
        await self._bump_version()
