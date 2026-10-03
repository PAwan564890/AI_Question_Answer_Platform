"""One-shot initialisation: create collections, then seed the first ADMIN.

Run with ``python -m app.database.seed``. The admin credentials come from the
``ADMIN_USERNAME`` / ``ADMIN_PASSWORD`` environment variables; nothing is
hard-coded and the password is never printed. Running it again is safe: an
existing user is left untouched.
"""

import asyncio
import logging
import sys

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.database.bootstrap import ensure_collections
from app.database.client import create_qdrant_client
from app.models import Role
from app.repositories.users import UserRepository
from app.schemas.users import UserCreate

logger = logging.getLogger("app.seed")


async def run() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    client = create_qdrant_client(settings)
    try:
        await ensure_collections(client, settings.embedding_dim)
        logger.info("schema_ready")

        if not settings.admin_username or not settings.admin_password:
            logger.error("ADMIN_USERNAME and ADMIN_PASSWORD must be set to seed the first admin.")
            return 1
        try:
            # Reuse the API's own validation so the seed cannot create a weak admin.
            new_admin = UserCreate(
                username=settings.admin_username,
                password=settings.admin_password,
                role=Role.ADMIN,
            )
        except ValidationError as exc:
            reasons = "; ".join(e["msg"] for e in exc.errors())
            logger.error("Admin credentials rejected: %s", reasons)
            return 1

        users = UserRepository(client)
        if await users.get_by_username(new_admin.username):
            logger.info("admin_exists", extra={"admin_username": new_admin.username})
            return 0
        password_hash = await asyncio.to_thread(hash_password, new_admin.password)
        user = await users.create(new_admin.username, password_hash, Role.ADMIN)
        logger.info("admin_created", extra={"user_id": user.id})
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
