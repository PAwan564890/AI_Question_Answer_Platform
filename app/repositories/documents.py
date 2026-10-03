"""Knowledge-base storage: text chunks and their embeddings (the RAG index)."""

import uuid
from datetime import UTC, datetime

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm

from app.database.client import DOCUMENTS
from app.models import DocumentInfo, RetrievedChunk


def _doc_filter(doc_id: str) -> qm.Filter:
    return qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])


class DocumentRepository:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def add(
        self,
        *,
        title: str,
        source: str | None,
        created_by: str,
        embedding_model: str,
        chunks: list[str],
        vectors: list[list[float]],
    ) -> DocumentInfo:
        doc_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        points = [
            qm.PointStruct(
                id=str(uuid.uuid5(uuid.UUID(doc_id), str(index))),
                vector=vector,
                payload={
                    "doc_id": doc_id,
                    "title": title,
                    "source": source,
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                    "text": text,
                    "embedding_model": embedding_model,
                    "created_by": created_by,
                    "created_at": now.isoformat(),
                    "created_ts": now.timestamp(),
                },
            )
            for index, (text, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        await self._client.upsert(DOCUMENTS, points=points)
        return DocumentInfo(doc_id, title, source, len(chunks), created_by, now)

    async def search(
        self, vector: list[float], top_k: int, score_threshold: float
    ) -> list[RetrievedChunk]:
        response = await self._client.query_points(
            DOCUMENTS,
            query=vector,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            RetrievedChunk(
                doc_id=payload["doc_id"],
                title=payload["title"],
                chunk_index=payload["chunk_index"],
                text=payload["text"],
                score=round(float(point.score), 4),
            )
            for point in response.points
            if (payload := point.payload)
        ]

    async def list(self, limit: int, offset: int) -> list[DocumentInfo]:
        # Chunk 0 of every document carries the document-level metadata.
        points, _ = await self._client.scroll(
            DOCUMENTS,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="chunk_index", match=qm.MatchValue(value=0))]
            ),
            limit=limit + offset,
            order_by=qm.OrderBy(key="created_ts", direction=qm.Direction.DESC),
            with_payload=True,
        )
        return [
            DocumentInfo(
                doc_id=payload["doc_id"],
                title=payload["title"],
                source=payload.get("source"),
                chunk_count=payload["chunk_count"],
                created_by=payload["created_by"],
                created_at=datetime.fromisoformat(payload["created_at"]),
            )
            for point in points[offset:]
            if (payload := point.payload)
        ]

    async def delete(self, doc_id: str) -> bool:
        """Delete every chunk of a document. Returns False if it did not exist."""
        existing = await self._client.count(DOCUMENTS, count_filter=_doc_filter(doc_id), exact=True)
        if existing.count == 0:
            return False
        await self._client.delete(
            DOCUMENTS, points_selector=qm.FilterSelector(filter=_doc_filter(doc_id))
        )
        return True
