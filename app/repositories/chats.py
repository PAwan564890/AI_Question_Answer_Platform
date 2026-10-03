"""Chat/usage records and admin audit events (payload-only Qdrant collections)."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm

from app.database.client import AUDIT_EVENTS, CHAT_RECORDS
from app.models import ChatRecord


def _to_record(point: qm.Record) -> ChatRecord:
    p = dict(point.payload or {})
    p.pop("created_ts", None)
    p["created_at"] = datetime.fromisoformat(p["created_at"])
    return ChatRecord(id=str(point.id), **p)


class ChatRepository:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def add(self, record: ChatRecord) -> None:
        payload = asdict(record)
        payload.pop("id")
        payload["created_at"] = record.created_at.isoformat()
        payload["created_ts"] = record.created_at.timestamp()  # numeric copy for sorting
        await self._client.upsert(
            CHAT_RECORDS, points=[qm.PointStruct(id=record.id, vector={}, payload=payload)]
        )

    async def list(self, user_id: str | None, limit: int, offset: int) -> list[ChatRecord]:
        """Newest first. ``user_id=None`` returns every user's records (admin view)."""
        query_filter = None
        if user_id is not None:
            query_filter = qm.Filter(
                must=[qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id))]
            )
        # Qdrant's ordered scroll has no numeric offset, so read limit+offset
        # rows and slice. The route caps offset, which keeps this bounded.
        points, _ = await self._client.scroll(
            CHAT_RECORDS,
            scroll_filter=query_filter,
            limit=limit + offset,
            order_by=qm.OrderBy(key="created_ts", direction=qm.Direction.DESC),
            with_payload=True,
        )
        return [_to_record(p) for p in points[offset:]]


class AuditRepository:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def add(self, actor_id: str, action: str, target_id: str, changes: dict) -> None:
        now = datetime.now(UTC)
        payload = {
            "actor_id": actor_id,
            "action": action,
            "target_id": target_id,
            "changes": changes,
            "created_at": now.isoformat(),
            "created_ts": now.timestamp(),
        }
        await self._client.upsert(
            AUDIT_EVENTS,
            points=[qm.PointStruct(id=str(uuid.uuid4()), vector={}, payload=payload)],
        )
