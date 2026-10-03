"""Operational endpoints: liveness, readiness, health, metrics.

* ``/health/live``  - "is this process running?"  No dependency checks, so a
  database outage never makes the orchestrator restart healthy processes.
* ``/health/ready`` - "should the load balancer send traffic here?"  503 unless
  Qdrant answers and the collections exist. Redis is reported but does not
  gate readiness: /chat is designed to keep working without Redis (fail open),
  and a readiness probe that failed on Redis would make the load balancer
  remove every replica at once and turn a degraded service into an outage.
* ``/health``       - the human/dashboard view, including degraded states
  (for example Redis down: chat still works, without cache or shared limits).
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from qdrant_client.http.exceptions import ApiException
from redis.exceptions import RedisError

from app.api.deps import ContainerDep, require_metrics_access
from app.container import Container
from app.database.client import ALL_COLLECTIONS
from app.monitoring import metrics

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ops"])

_CHECK_TIMEOUT_SECONDS = 2.0


async def _database_ok(container: Container) -> bool:
    try:
        response = await asyncio.wait_for(
            container.qdrant.get_collections(), timeout=_CHECK_TIMEOUT_SECONDS
        )
        ok = {c.name for c in response.collections} >= set(ALL_COLLECTIONS)
    except (ApiException, TimeoutError, OSError):
        ok = False
    metrics.DEPENDENCY_UP.labels(dependency="database").set(1 if ok else 0)
    return ok


async def _redis_ok(container: Container) -> bool:
    try:
        ok = bool(await asyncio.wait_for(container.redis.ping(), timeout=_CHECK_TIMEOUT_SECONDS))
    except (RedisError, TimeoutError, OSError):
        ok = False
    metrics.DEPENDENCY_UP.labels(dependency="redis").set(1 if ok else 0)
    return ok


def _llm_status(container: Container) -> str:
    primary, fallback = container.gateway.primary, container.gateway.fallback
    if primary.name == "mock":
        return "mock"
    if primary.configured:
        return "configured"
    if fallback is not None and fallback.configured:
        return "fallback_only"
    return "unconfigured"


def _embeddings_status(container: Container) -> str:
    if container.embedder.configured:
        return container.embedder.name
    return "unconfigured"


def _ok_or_fail(healthy: bool) -> str:
    return "ok" if healthy else "fail"


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness probe")
async def ready(container: ContainerDep) -> JSONResponse:
    database, redis = await asyncio.gather(_database_ok(container), _redis_ok(container))
    is_ready = database
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": {
                "database": _ok_or_fail(database),
                "redis": _ok_or_fail(redis),
            },
        },
    )


@router.get("/health", summary="Aggregate application health")
async def health(container: ContainerDep) -> JSONResponse:
    database, redis = await asyncio.gather(_database_ok(container), _redis_ok(container))
    llm = _llm_status(container)
    if not database:
        status = "unhealthy"  # no users, no persistence: nothing useful can be served
    elif not redis or llm in ("unconfigured", "fallback_only"):
        status = "degraded"
    else:
        status = "ok"
    return JSONResponse(
        status_code=503 if status == "unhealthy" else 200,
        content={
            "status": status,
            "checks": {
                "database": _ok_or_fail(database),
                "redis": _ok_or_fail(redis),
                "llm": llm,
                "embeddings": _embeddings_status(container),
            },
            "version": container.settings.app_version,
        },
    )


@router.get("/metrics", summary="Prometheus metrics (ADMIN token or scrape token)")
async def prometheus_metrics(_: Annotated[None, Depends(require_metrics_access)]) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
