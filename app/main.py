"""Application factory: middleware, exception handling and router wiring."""

import logging
import re
import socket
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import ApiException

from app.api.routes import admin, auth, chat, documents, ops
from app.container import build_container
from app.core.config import DEV_JWT_SECRET, Settings, get_settings
from app.core.errors import error_body, register_exception_handlers
from app.core.logging import configure_logging, request_id_var
from app.monitoring import metrics

logger = logging.getLogger("app")

_HOSTNAME = socket.gethostname()  # the container id in Docker: shows which replica answered
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _choose_request_id(request: Request) -> str:
    """Reuse the caller's X-Request-ID if it looks safe; otherwise generate one.

    Accepting arbitrary text would let a client inject fake lines into the logs.
    """
    incoming = request.headers.get("x-request-id", "")
    if _VALID_REQUEST_ID.match(incoming):
        return incoming
    return str(uuid.uuid4())


def _error_response(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, request_id))


def _install_request_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next) -> Response:
        """Runs around every request: request id, size limit, metrics, log, headers."""
        request_id = _choose_request_id(request)
        request.state.request_id = request_id
        token = request_id_var.set(request_id)  # makes the id available to every log line
        started = time.perf_counter()
        try:
            response = await _handle(request, call_next, request_id)
            elapsed = time.perf_counter() - started

            # The route *template* ("/admin/users/{user_id}"), never the raw
            # URL, keeps metric label cardinality bounded.
            route = request.scope.get("route")
            route_label = getattr(route, "path", "unmatched")
            status = response.status_code
            metrics.HTTP_REQUESTS.labels(request.method, route_label, str(status)).inc()
            metrics.HTTP_DURATION.labels(request.method, route_label).observe(elapsed)
            if status >= 400:
                metrics.HTTP_ERRORS.labels(route_label, str(status)).inc()

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Served-By"] = _HOSTNAME
            for header, value in _SECURITY_HEADERS.items():
                response.headers.setdefault(header, value)

            if not route_label.startswith("/health"):  # probes would drown the log
                logger.info(
                    "request",
                    extra={
                        "method": request.method,
                        "route": route_label,
                        "status": status,
                        "latency_ms": int(elapsed * 1000),
                        "user_id": getattr(request.state, "user_id", None),
                    },
                )
            return response
        finally:
            request_id_var.reset(token)

    async def _handle(request: Request, call_next, request_id: str) -> Response:
        """Call the route. Turn the failures no route should handle into clean JSON errors."""
        content_length = request.headers.get("content-length", "0")
        if content_length.isdigit() and int(content_length) > settings.max_body_bytes:
            return _error_response(
                413, "PAYLOAD_TOO_LARGE", "The request body is too large.", request_id
            )
        try:
            return await call_next(request)
        except ApiException:
            logger.exception("database_error")
            return _error_response(
                503, "DATABASE_UNAVAILABLE", "The database is temporarily unavailable.", request_id
            )
        except Exception:
            # Last line of defence: log the stack trace, return none of it.
            logger.exception("unhandled_exception")
            return _error_response(
                500, "INTERNAL_ERROR", "An unexpected error occurred.", request_id
            )


def create_app(settings: Settings | None = None, **overrides) -> FastAPI:
    """Build the app. ``overrides`` lets tests inject fake Qdrant/Redis/LLM objects."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    if settings.jwt_secret == DEV_JWT_SECRET:
        logger.warning("Using the built-in development JWT secret. Never do this in production.")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("startup", extra={"env": settings.app_env, "llm": settings.llm_provider})
        yield
        # Runs on SIGTERM after uvicorn has finished in-flight requests.
        await app.state.container.aclose()
        logger.info("shutdown")

    app = FastAPI(
        title="AI Question-Answering Platform",
        version=settings.app_version,
        description="JWT-secured, rate-limited, observable Q&A API with RAG over Qdrant.",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.container = build_container(settings, **overrides)

    if settings.cors_origins:
        # Explicit origins only, and no credentials: the API uses bearer tokens
        # in a header, not cookies, so browsers never need to send credentials.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )

    _install_request_middleware(app, settings)
    register_exception_handlers(app)
    for module in (auth, chat, documents, admin, ops):
        app.include_router(module.router)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn app.main:app_factory --factory``."""
    return create_app()
