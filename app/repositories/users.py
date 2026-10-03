"""User persistence in the Qdrant ``users`` collection.

How this works: a vector database has no UNIQUE constraint, so uniqueness of
usernames is obtained by construction. The point id is a UUIDv5 derived from
the lower-cased username, which means the same username always maps to the
same point and two users can never share a name.
"""

import uuid
from datetime import UTC, datetime

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm

from app.database.client import USERS
from app.models import Role, User

_USER_NAMESPACE = uuid.UUID("6f0b6a52-6c1a-4b5e-9d55-0f6f2a1c9e11")


def user_id_for(username: str) -> str:
    return str(uuid.uuid5(_USER_NAMESPACE, username.lower()))


def _to_user(point: qm.Record) -> User:
    p = point.payload or {}
    last_login = p.get("last_login_at")
    return User(
        id=str(point.id),
        username=p["username"],
        password_hash=p["password_hash"],
        role=Role(p["role"]),
        is_active=p["is_active"],
        created_at=datetime.fromisoformat(p["created_at"]),
        last_login_at=datetime.fromisoformat(last_login) if last_login else None,
    )


class UserRepository:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def get_by_id(self, user_id: str) -> User | None:
        try:
            uuid.UUID(user_id)
        except ValueError:
            return None
        points = await self._client.retrieve(USERS, ids=[user_id], with_payload=True)
        return _to_user(points[0]) if points else None

    async def get_by_username(self, username: str) -> User | None:
        return await self.get_by_id(user_id_for(username))

    async def create(self, username: str, password_hash: str, role: Role) -> User:
        now = datetime.now(UTC)
        user = User(
            id=user_id_for(username),
            username=username,
            password_hash=password_hash,
            role=role,
            is_active=True,
            created_at=now,
        )
        payload = {
            "username": user.username,
            "password_hash": user.password_hash,
            "role": user.role.value,
            "is_active": True,
            "created_at": now.isoformat(),
            "created_ts": now.timestamp(),
            "last_login_at": None,
        }
        await self._client.upsert(
            USERS, points=[qm.PointStruct(id=user.id, vector={}, payload=payload)]
        )
        return user

    async def update_fields(self, user_id: str, fields: dict) -> None:
        """Merge ``fields`` into the stored payload (other keys are untouched)."""
        await self._client.set_payload(USERS, payload=fields, points=[user_id])

    async def touch_last_login(self, user_id: str) -> None:
        await self.update_fields(user_id, {"last_login_at": datetime.now(UTC).isoformat()})

    async def list(self, limit: int, offset: int) -> list[User]:
        points, _ = await self._client.scroll(
            USERS,
            limit=limit + offset,
            order_by=qm.OrderBy(key="created_ts", direction=qm.Direction.ASC),
            with_payload=True,
        )
        return [_to_user(p) for p in points[offset:]]
