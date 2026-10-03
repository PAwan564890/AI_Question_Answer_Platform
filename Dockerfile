# syntax=docker/dockerfile:1

# ---- Stage 1: build the virtual environment -------------------------------
# Anything needed only to *install* dependencies stays in this stage and never
# reaches the image that runs in production.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Run as an unprivileged user: a compromised process cannot modify the image
# contents or act as root inside the container.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app

USER app
EXPOSE 8000

# Liveness only (no dependency checks): "is this process answering HTTP?"
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

# Exec form so uvicorn is PID 1 and receives SIGTERM directly. On SIGTERM it
# stops accepting connections and gives in-flight requests up to 30 s to finish.
# One worker per container: scale by adding containers, not processes.
# Keep-alive (75 s) is longer than the load balancer's idle timeout (nginx: 60 s),
# so the proxy, not the app, closes idle connections and no request is ever sent
# on a connection the app has just closed.
CMD ["uvicorn", "app.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "30", "--timeout-keep-alive", "75", "--no-access-log"]
