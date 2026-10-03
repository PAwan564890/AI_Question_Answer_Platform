"""End-to-end smoke test against a running stack (standard library only).

    docker compose up --build -d --scale app=3
    python scripts/smoke_test.py                 # default http://localhost:8000

Written in Python rather than bash so the same script runs on Windows, macOS
and Linux. Admin credentials are read from .env; nothing secret is printed.
Exit code 0 means every check passed.
"""

import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
served_by: set[str] = set()
failures = 0


def read_env() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def call(method: str, path: str, body: dict | None = None, token: str | None = None):
    """Return (status, parsed JSON or text, headers). Never raises on HTTP errors."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status, raw, response_headers = response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        status, raw, response_headers = error.code, error.read(), error.headers
    if response_headers.get("X-Served-By"):
        served_by.add(response_headers["X-Served-By"])
    text = raw.decode()
    try:
        return status, json.loads(text), response_headers
    except ValueError:
        return status, text, response_headers


def check(name: str, condition: bool, detail: str = "") -> None:
    global failures
    failures += 0 if condition else 1
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def login(username: str, password: str) -> str:
    status, body, _ = call("POST", "/auth/login", {"username": username, "password": password})
    check(f"login as {username}", status == 200, f"status {status}")
    return body["access_token"] if status == 200 else ""


def main() -> int:
    env = read_env()

    for _ in range(60):  # wait for the stack to become ready
        try:
            if call("GET", "/health/ready")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(2)
    status, body, _ = call("GET", "/health")
    check("GET /health is ok", status == 200 and body.get("status") == "ok", json.dumps(body))
    check("GET /health/live", call("GET", "/health/live")[0] == 200)

    check("POST /chat without token -> 401", call("POST", "/chat", {"question": "hi"})[0] == 401)
    check("GET /metrics without token -> 401", call("GET", "/metrics")[0] == 401)

    admin = login(env["ADMIN_USERNAME"], env["ADMIN_PASSWORD"])

    # Fresh throwaway accounts per run, with random passwords.
    suffix = secrets.token_hex(3)
    password = secrets.token_urlsafe(12) + "a1"
    user_name, reader_name = f"smoke_user_{suffix}", f"smoke_reader_{suffix}"
    for name, role in ((user_name, "USER"), (reader_name, "READ_ONLY")):
        status, _, _ = call(
            "POST", "/admin/users", {"username": name, "password": password, "role": role}, admin
        )
        check(f"admin creates {role} account", status == 201, f"status {status}")
    user, reader = login(user_name, password), login(reader_name, password)

    status, _, _ = call("GET", "/admin/users", token=user)
    check("USER on /admin/users -> 403", status == 403)
    status, _, _ = call("POST", "/chat", {"question": "hi"}, reader)
    check("READ_ONLY on POST /chat -> 403", status == 403)

    marker = f"zephyr{suffix}"
    status, doc, _ = call(
        "POST",
        "/documents",
        {
            "title": "Smoke test note",
            "text": f"The {marker} protocol uses port 4242 for telemetry uploads.",
        },
        admin,
    )
    check("admin ingests a document into Qdrant", status == 201, f"status {status}")

    question = f"Which port does the {marker} protocol use?"
    status, first, _ = call("POST", "/chat", {"question": question}, user)
    check("POST /chat answers via the LLM gateway", status == 200, f"status {status}")
    check(
        "answer is grounded in the retrieved document (RAG)",
        status == 200 and "4242" in first["answer"] and len(first["sources"]) >= 1,
    )
    check("token usage and latency are reported", status == 200 and first["latency_ms"] >= 0)

    status, second, _ = call("POST", "/chat", {"question": question}, user)
    check("identical question is served from the Redis cache", status == 200 and second["cached"])

    status, hits, _ = call("POST", "/documents/search", {"query": f"{marker} telemetry"}, reader)
    check("READ_ONLY can run a vector search", status == 200 and len(hits["results"]) >= 1)

    status, history, _ = call("GET", "/chat/history?limit=5", token=user)
    check(
        "chat records were persisted in Qdrant",
        status == 200 and len(history) == 2 and history[0]["cached"] is True,
    )

    # Rate limit: keep asking distinct questions until the shared limiter says stop.
    limit = int(env.get("CHAT_RATE_LIMIT", "20"))
    statuses = []
    retry_after = None
    for i in range(limit + 5):
        status, _, headers = call("POST", "/chat", {"question": f"rate limit probe {i}"}, user)
        statuses.append(status)
        if status == 429:
            retry_after = headers.get("Retry-After")
            break
    check(
        f"rate limit: 429 after {limit} requests per window, across replicas",
        statuses[-1] == 429 and statuses.count(200) == limit - 2 and retry_after is not None,
        f"{statuses.count(200)} more allowed after the 2 earlier calls, Retry-After={retry_after}",
    )

    status, metrics, _ = call("GET", "/metrics", token=admin)
    expected = ("http_requests_total", "llm_requests_total", "cache_requests_total")
    check(
        "GET /metrics (ADMIN) exposes Prometheus series",
        status == 200 and all(name in metrics for name in expected),
    )

    if doc and isinstance(doc, dict) and doc.get("doc_id"):
        status, _, _ = call("DELETE", f"/documents/{doc['doc_id']}", token=admin)
        check("cleanup: document deleted", status == 204)

    print(f"\nReplicas that answered (X-Served-By): {sorted(served_by)}")
    print("RESULT:", "ALL CHECKS PASSED" if failures == 0 else f"{failures} CHECK(S) FAILED")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
