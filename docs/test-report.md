# Test report

All results below were produced on **2026-10-03** on one laptop (Intel Core i5-12500H, 16 GB RAM,
Windows 11, Python 3.12.10, Docker Desktop 29.8.1). Raw command output is in
[`docs/evidence/`](evidence/). Nothing here was run in a cloud, and no real LLM provider was
called: the LLM is the mock provider throughout.

## 1. Summary

| Check | Command | Result | Evidence |
|---|---|---|---|
| Unit + API tests | `pytest` | **150 passed**, 3 skipped (the integration tests) | [pytest-coverage.txt](evidence/pytest-coverage.txt) |
| Coverage | `pytest --cov=app --cov-report=term-missing` | **96 %** (1,703 statements, 67 missed) | same file |
| Integration tests (real Redis 7.4 + Qdrant 1.19.1 containers) | `RUN_INTEGRATION=1 pytest -m integration` | **3 passed** | [pytest-integration.txt](evidence/pytest-integration.txt) |
| Lint, formatting, types | `ruff check .` · `ruff format --check .` · `mypy app` | Clean | — |
| Fresh clone, following only the README | clone → `make_env.py` → `docker compose up` → smoke test → new virtualenv → `pytest` | Stack healthy; smoke 21/21; 150 passed | [audit-report.md §7](audit-report.md) |
| Dependency audit | `pip-audit -r requirements.txt` | **No known vulnerabilities found** | [pip-audit.txt](evidence/pip-audit.txt) |
| End-to-end smoke test, fresh volumes, 3 replicas | `python scripts/smoke_test.py` | **21 / 21 checks passed**; three distinct replicas answered | [smoke-test.txt](evidence/smoke-test.txt) |
| Container user | `docker compose exec app id` | `uid=10001(app)` (non-root) | [compose-ps.txt](evidence/compose-ps.txt) |
| Load tests (mock LLM) | `scripts/load_test.py` | See [scaling-analysis.md §12](scaling-analysis.md#12-what-was-measured); an independent re-run reproduced the results (52.7 vs 53.0 req/s; identical shedding counts) | [load-test.txt](evidence/load-test.txt), [load-test-rerun.txt](evidence/load-test-rerun.txt) |
| Real LLM provider | `python scripts/verify_llm.py` | **Not run: no API key available.** The script exits with code 2 and sends nothing | [audit-report.md §4](audit-report.md) |
| Kubernetes manifests | YAML parse only | 11 resources parsed; **not validated by kubectl, not applied** | [k8s-yaml-parse.txt](evidence/k8s-yaml-parse.txt) |

No test failed in the final run. `app/database/seed.py` (the init job) is excluded from the
coverage figure by configuration; it is exercised by the Compose `init` service instead.

## 2. How the tests are built

* **No Docker, network or API key needed** for the main suite: Qdrant runs in the client's
  in-memory mode, Redis is `fakeredis`, the LLM is `MockProvider`. The whole suite takes about 20 s.
* API tests drive the real FastAPI app through `httpx.ASGITransport`, so middleware, dependency
  injection, exception handlers and routing are all exercised.
* Time-dependent logic (backoff, circuit breaker, rate-limit windows) uses injected clocks and
  sleep functions, so those tests are deterministic and instant.
* Failure modes are scripted on the mock: `provider.script("timeout", "server_error", "ok")`.
* Redis outages are simulated by disconnecting the fake server; Qdrant outages by patching the
  client to raise its real exception type.
* Integration tests (opt-in) repeat the critical paths against real servers, because the fakes
  cannot prove atomicity or server-side behaviour such as payload indexes and ordered scroll.

## 3. Coverage of the required test matrix

| Area | Requirement | Test |
|---|---|---|
| Unit | Password hash / verify, salting | `test_security.py::test_password_hash_roundtrip_and_salting` |
| Unit | JWT create/verify, expiry, tamper, wrong secret, `alg=none`, missing claims | `test_security.py` (5 tests) |
| Unit | Weak `JWT_SECRET` refused in prod | `test_security.py::test_prod_refuses_weak_jwt_secret` |
| Unit | Schema validation: empty, whitespace, too long, bad types, unknown fields | `test_schemas.py` |
| Unit | Retry/backoff with injected clock and jitter; bounded retries; deadline | `test_gateway.py` |
| Unit | Circuit-breaker transitions | `test_gateway.py::test_circuit_breaker_transitions`, `…opens_and_fails_fast_then_recovers` |
| Unit | Concurrency limit sheds load | `test_gateway.py::test_concurrency_limit_sheds_load` |
| Unit | Cache-key isolation (user, model, temperature, prompt version, provider, RAG flag, KB version) | `test_redis_services.py::test_cache_key_isolation` |
| Unit | Rate-limiter window logic | `test_redis_services.py::test_fixed_window_counts_and_resets` |
| Unit | Chunking, embeddings, prompt delimiters | `test_rag_and_adapters.py` |
| Unit | OpenAI-compatible adapter: success, usage null, 401/403/429/5xx/400, malformed, timeout, network error, unconfigured | `test_rag_and_adapters.py` (stubbed HTTP) |
| Integration | Bootstrap idempotent; CRUD on real Qdrant | `test_real_services.py::test_bootstrap_is_idempotent_and_users_roundtrip` |
| Integration | Vector search on real Qdrant | `…::test_vector_search_on_real_qdrant` |
| Integration | Rate limit across two clients on real Redis (50 concurrent hits → exactly 20 allowed) | `…::test_rate_limiter_is_atomic_under_concurrency_on_real_redis` |
| Auth | Missing / malformed / wrong-scheme / bad-signature / expired token, unknown user → 401 | `test_auth_api.py::test_protected_route_returns_401` |
| Auth | Wrong role → 403; full role matrix | `test_auth_api.py::test_rbac_matrix` (12 rows × 3 roles) |
| Auth | Password change invalidates older tokens | `…test_password_change_invalidates_existing_tokens` |
| Auth | Admin actions audited, without secrets | `…test_admin_actions_are_audited_without_secrets` |
| Auth | Inactive user → **401** at login and with an existing token | `…login_failures_share_one_generic_message`, `…deactivated_user_token_stops_working_immediately` |
| Auth | Role from database, not from token | `…test_role_comes_from_database_not_from_token` |
| Auth | Login success / failure / throttling / fail-closed without Redis | `test_auth_api.py` |
| Chat | Valid request via mock; persisted | `test_chat_api.py::test_chat_success_shape_and_persistence` |
| Chat | Invalid body → 422; READ_ONLY → 403 | `…invalid_body_is_422`, RBAC matrix |
| Chat | Timeout → 504 after bounded retries | `…provider_timeout_returns_504_after_bounded_retries` |
| Chat | 5xx → retry, then fallback or 503 | `…5xx_retries_then_succeeds`, `…uses_fallback_when_configured`, `…without_fallback_is_503…` |
| Chat | Provider 429 honours `Retry-After` | `…provider_429_honours_retry_after`, `test_gateway.py::test_rate_limit_honours_retry_after` |
| Chat | Auth error not retried | `…provider_auth_error_is_not_retried` |
| Chat | Circuit opens after threshold | `…circuit_opens_after_threshold_and_fails_fast` |
| Chat | Rate limit → 429 + `Retry-After` | `…chat_rate_limit_returns_429_with_retry_after` |
| Chat | Cache hit: `cached=true`, provider skipped; no leak between users; errors not cached | three tests in `test_chat_api.py` |
| Chat | Error responses contain no internals | `…without_fallback_is_503_with_no_internals`, `test_ops_api.py::test_unexpected_exception_is_a_500_without_internals` |
| Chat | RAG grounding, sources, cache invalidation on ingest | `…rag_answer_uses_retrieved_context_and_cites_sources` |
| Chat | Missing API key → safe 503, health degraded | `…unconfigured_real_provider_is_a_safe_503` |
| Health | `/health` ok; Redis down → degraded but still ready; Qdrant down → unhealthy and not ready; live unaffected | `test_ops_api.py` (3 tests) |
| Metrics | Expected names; counters increment; low-cardinality labels; ADMIN only | `test_ops_api.py` (5 tests) |
| Docker smoke | Compose up, login, chat, health, metrics, record stored, rate limit across replicas | `scripts/smoke_test.py` |

## 4. Manual verification on the running stack

```text
$ docker compose stop redis
$ curl localhost:8000/health/live   -> 200
$ curl localhost:8000/health        -> 200 {"status":"degraded","checks":{"database":"ok","redis":"fail","llm":"mock","embeddings":"hash"},"version":"1.0.0"}
$ curl localhost:8000/health/ready  -> 200 {"status":"ready","checks":{"database":"ok","redis":"fail"}}   # Redis does not gate readiness
$ docker compose start redis
  (a few seconds later) /health -> {"status":"ok", ...}
```

```text
$ docker compose down && docker compose up -d       # volumes kept
  admin login still works; users and chat records created before the restart are still listed
$ docker compose logs init
  {"level": "INFO", "logger": "app.seed", "message": "admin_exists", ...}   # seed is idempotent
```

## 5. Problems found by testing, and what was done

| Found by | Problem | Resolution |
|---|---|---|
| Load test | At high concurrency against one replica the client occasionally got a connection `ReadError` | uvicorn keep-alive raised to 75 s (above nginx's 60 s upstream idle timeout), so the proxy closes idle connections, not the app |
| Load test | Throughput looked far below the prediction | Comparing client latency with nginx `request_time` and the app log showed the load generator itself was the bottleneck; timings were added to the nginx access log and the generator's limits are documented |
| Load test procedure | Recreating one Compose service silently scaled the API back to one replica | The replica count is now declared in the Compose file (`APP_REPLICAS`, default 3) |
| Retrieval check | With 384 hash buckets, collisions produced random similarity between unrelated texts, and realistic-length chunks scored below the threshold | 2048 buckets, log-scaled word weights, a larger stop-word list, threshold 0.08 |
| Integration run | Host port 6379 was already in use | Development ports are configurable (`REDIS_DEV_PORT`, `QDRANT_DEV_PORT`) |
| Final audit | Readiness failed on Redis although chat survives a Redis outage | Readiness gates on the database only |
| Final audit | A password change left older tokens valid | Tokens issued before the change are rejected |
| Final audit | Knowledge-base changes were not audited; the audit trail was unreadable | Audit events added; `GET /admin/audit` |
| Final audit | nginx returned an HTML page for oversized bodies | Same JSON envelope (verified with a 400 kB body) |
| Final audit | `mypy` reported 14 issues | Fixed; `mypy` added to CI |
| Demo rehearsal | The script changed directory and broke its own `docker compose` commands | Script corrected; every command re-run |

## 6. Not tested

* Any real LLM provider or real embedding service.
* Any cloud deployment; Kubernetes manifests on a cluster; the GitHub Actions workflow.
* 500 requests/second, sustained load, or the gateway's true capacity (the load generator
  saturated first).
* Killing an API replica or Qdrant under load (chaos testing); backup and restore.
* TLS, secret scanning of Git history, container image scanning, penetration testing.
