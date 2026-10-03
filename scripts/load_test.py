"""Small closed-loop load generator for POST /chat.

    python scripts/load_test.py --requests 2000 --concurrency 50

What it measures: the gateway tier (nginx + FastAPI + Redis + Qdrant) with the
MOCK LLM, on this machine. It says nothing about a real LLM provider, whose
latency and quotas dominate in production. Raise CHAT_RATE_LIMIT in .env first,
otherwise most requests are (correctly) rejected with 429.

Caveat: this generator is a single Python process. Above roughly 100 req/s it
becomes the bottleneck itself, so compare its numbers with the server-side
timings in the nginx access log (request_time) before drawing conclusions.

Each request asks a distinct question, so the response cache is bypassed and
every request exercises the full path. Credentials are read from .env.
"""

import argparse
import asyncio
import statistics
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def read_env() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


async def run(url: str, total: int, concurrency: int) -> None:
    env = read_env()
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(base_url=url, timeout=60, limits=limits) as client:
        login = await client.post(
            "/auth/login",
            json={"username": env["ADMIN_USERNAME"], "password": env["ADMIN_PASSWORD"]},
        )
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        latencies: list[float] = []
        statuses: Counter[int | str] = Counter()
        replicas: Counter[str] = Counter()
        queue: asyncio.Queue[int] = asyncio.Queue()
        for i in range(total):
            queue.put_nowait(i)
        run_id = int(time.time())

        async def worker() -> None:
            while True:
                try:
                    i = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                started = time.perf_counter()
                try:
                    response = await client.post(
                        "/chat",
                        json={"question": f"load test {run_id} question {i}"},
                        headers=headers,
                    )
                except httpx.HTTPError as exc:
                    statuses[type(exc).__name__] += 1  # connection-level failure
                    continue
                finally:
                    latencies.append(time.perf_counter() - started)
                statuses[response.status_code] += 1
                replicas[response.headers.get("x-served-by", "?")] += 1

        started = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        elapsed = time.perf_counter() - started

    latencies.sort()

    def percentile(p: float) -> float:
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))] * 1000

    print(f"requests={total} concurrency={concurrency} duration={elapsed:.2f}s")
    print(f"throughput={total / elapsed:.1f} req/s")
    print(f"status codes: {dict(sorted(statuses.items(), key=str))}")
    print(
        f"latency ms: mean={statistics.mean(latencies) * 1000:.1f} p50={percentile(0.50):.1f} "
        f"p95={percentile(0.95):.1f} p99={percentile(0.99):.1f} max={latencies[-1] * 1000:.1f}"
    )
    print(f"requests per replica: {dict(replicas)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(run(args.url, args.requests, args.concurrency))
