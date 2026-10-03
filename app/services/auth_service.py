"""Login and user administration (business logic; no HTTP objects here)."""

import asyncio
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.security import (
    create_access_token,
    dummy_password_hash,
    hash_password,
    verify_password,
)
from app.models import User
from app.repositories.chats import AuditRepository
from app.repositories.users import UserRepository, user_id_for
from app.schemas.users import TokenResponse, UserCreate, UserUpdate
from app.services.rate_limiter import LoginThrottle

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, settings: Settings, users: UserRepository, throttle: LoginThrottle) -> None:
        self._settings = settings
        self._users = users
        self._throttle = throttle

    async def login(self, username: str, password: str, client_ip: str) -> TokenResponse:
        await self._throttle.ensure_not_locked(username, client_ip)

        user = await self._users.get_by_username(username)
        # Always verify a hash, even for unknown users, so both paths take
        # about the same time. Argon2 is CPU-heavy by design, so it runs in a
        # worker thread instead of blocking the event loop.
        password_hash = user.password_hash if user else dummy_password_hash()
        password_ok = await asyncio.to_thread(verify_password, password, password_hash)

        if user is None or not password_ok or not user.is_active:
            await self._throttle.record_failure(username, client_ip)
            logger.warning(
                "login_failed", extra={"user_id": user.id if user else None, "client_ip": client_ip}
            )
            # One message for unknown user, wrong password and disabled account.
            raise AuthenticationError("Invalid username or password.", code="INVALID_CREDENTIALS")

        await self._throttle.reset(username, client_ip)
        await self._users.touch_last_login(user.id)
        token, expires_in = create_access_token(
            user_id=user.id, role=user.role.value, settings=self._settings
        )
        logger.info("login_succeeded", extra={"user_id": user.id})
        return TokenResponse(access_token=token, expires_in=expires_in)


class UserService:
    def __init__(self, users: UserRepository, audit: AuditRepository, redis: Redis) -> None:
        self._users = users
        self._audit = audit
        self._redis = redis

    async def list(self, limit: int, offset: int) -> list[User]:
        return await self._users.list(limit, offset)

    async def create(self, data: UserCreate, actor: User) -> User:
        # Qdrant has no unique constraint or transaction, so "check then
        # insert" could race between two replicas. A short Redis lock
        # (SET NX) makes the check-and-insert exclusive per username.
        lock_key = f"lock:user:{user_id_for(data.username)}"
        try:
            acquired = await self._redis.set(lock_key, "1", nx=True, ex=10)
        except RedisError as exc:
            raise ServiceUnavailableError("User creation is temporarily unavailable.") from exc
        if not acquired:
            raise ConflictError("A user with this username already exists.")
        try:
            if await self._users.get_by_username(data.username):
                raise ConflictError("A user with this username already exists.")
            password_hash = await asyncio.to_thread(hash_password, data.password)
            user = await self._users.create(data.username, password_hash, data.role)
        finally:
            try:
                await self._redis.delete(lock_key)
            except RedisError:
                logger.warning("user_lock_release_failed")  # it expires by itself in 10 s
        await self._audit.add(actor.id, "user.create", user.id, {"role": user.role.value})
        logger.info("admin_user_created", extra={"actor_id": actor.id, "target_id": user.id})
        return user

    async def update(self, user_id: str, data: UserUpdate, actor: User) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        # An admin must not be able to lock themselves (possibly the last admin) out.
        deactivating = data.is_active is False
        changing_role = data.role is not None and data.role != user.role
        if user.id == actor.id and (deactivating or changing_role):
            raise InvalidRequestError("Administrators cannot deactivate or demote themselves.")

        # `fields` is written to the database; `changes` goes to the audit trail
        # and never contains the password or its hash.
        fields: dict = {}
        changes: dict = {}
        if data.role is not None:
            fields["role"] = data.role.value
            changes["role"] = data.role.value
        if data.is_active is not None:
            fields["is_active"] = data.is_active
            changes["is_active"] = data.is_active
        if data.password is not None:
            fields["password_hash"] = await asyncio.to_thread(hash_password, data.password)
            # Tokens issued before this moment stop working (see get_current_user).
            fields["password_changed_ts"] = time.time()
            changes["password_changed"] = True
        await self._users.update_fields(user_id, fields)

        await self._audit.add(actor.id, "user.update", user_id, changes)
        logger.info("admin_user_updated", extra={"actor_id": actor.id, "target_id": user_id})
        updated = await self._users.get_by_id(user_id)
        if updated is None:
            raise NotFoundError("User not found.")
        return updated
