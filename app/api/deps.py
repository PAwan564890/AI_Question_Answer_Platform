"""FastAPI dependencies: the container, the current user, and role checks."""

import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.container import Container
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.models import Role, User

logger = logging.getLogger(__name__)

# auto_error=False: we raise our own 401 so the response uses the error envelope.
_bearer = HTTPBearer(auto_error=False, description="Paste the access_token from /auth/login.")
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def client_ip(request: Request) -> str:
    """Client address used for login throttling.

    ``X-Real-IP`` is trusted only when TRUST_PROXY_HEADERS=true, i.e. when the
    app is reachable solely through our own nginx, which overwrites the header.
    Otherwise a client could forge it to dodge the throttle.
    """
    container: Container = request.app.state.container
    if container.settings.trust_proxy_headers and (forwarded := request.headers.get("x-real-ip")):
        return forwarded
    return request.client.host if request.client else "unknown"


async def get_current_user(
    request: Request, credentials: Credentials, container: ContainerDep
) -> User:
    if credentials is None:
        raise AuthenticationError()
    claims = decode_access_token(credentials.credentials, container.settings)
    # The token proves identity; the database is the source of truth for the
    # account state. Loading the user on every request means a deactivated
    # account or a changed role takes effect immediately, not at token expiry.
    user = await container.users.get_by_id(str(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("The access token is no longer valid.", code="INVALID_TOKEN")
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: Role) -> Callable[..., Awaitable[User]]:
    """Dependency factory: allow only the listed roles (deny by default)."""

    async def _checker(request: Request, user: CurrentUser) -> User:
        if user.role not in roles:
            logger.warning(
                "authorization_denied",
                extra={"user_id": user.id, "role": user.role.value, "path": request.url.path},
            )
            raise PermissionDeniedError()
        return user

    return _checker


async def require_metrics_access(
    request: Request, credentials: Credentials, container: ContainerDep
) -> None:
    """/metrics is open to an ADMIN token or to the optional static scrape token."""
    scrape_token = container.settings.metrics_scrape_token
    if (
        credentials is not None
        and scrape_token
        and hmac.compare_digest(credentials.credentials.encode(), scrape_token.encode())
    ):
        return
    user = await get_current_user(request, credentials, container)
    if user.role is not Role.ADMIN:
        raise PermissionDeniedError()
