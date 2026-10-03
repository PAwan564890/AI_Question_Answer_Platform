# Final engineering audit

Date: 3 October 2026. Scope: the repository as committed, the running Docker Compose stack, and
a fresh clone. Method: every earlier claim was re-executed where execution was possible; where it
was not, that is stated. Raw output is in [`evidence/`](evidence/).

Status words used below:

* **Implemented** — code exists and was verified by a test or on the live stack.
* **Partial** — code exists but an important part is unverified or missing.
* **Documented only** — an explanation was asked for and is provided; no code is expected or present.
* **Not implemented** — absent.

## 1. Re-validation of earlier claims

| Earlier claim | Re-run during the audit | Outcome |
|---|---|---|
| 146 tests pass | `pytest` on the committed code before any change | **Reproduced**: 146 passed, 3 skipped |
| 96 % coverage | `pytest --cov=app` | **Reproduced**: 96 %. After the audit fixes: 150 passed, 96 % (1,644 statements, 62 missed) |
| Lint clean | `ruff check`, `ruff format --check` | Reproduced |
| No known vulnerabilities | `pip-audit -r requirements.txt` | Reproduced |
| 3 replicas behind nginx, Redis and Qdrant healthy | `docker compose ps`, `/health` | Reproduced |
| 21/21 smoke checks | `scripts/smoke_test.py` on the rebuilt stack **and** on a fresh clone | Reproduced twice |
| 53.0 req/s with 1 s simulated latency | Full load-test re-run | **Reproduced**: 52.7 req/s |
| 118.5 req/s with zero latency | Full load-test re-run | 111.9 req/s. Both are limited by the load generator (nginx measured a 25–26 ms median in both), so the difference is generator noise |
| Load shedding 300 × 200 / 300 × 503 | Re-run | Reproduced exactly |
| Real LLM integration works | Cannot be run: no API key available | **Not verifiable** — see section 4 |
| Type checking | Never run before the audit | Run now: 14 findings, all fixed; `mypy app` is clean |

## 2. Assessment compliance matrix

### 2.1 Core task

| Requirement | Implementation | Verification | Status | Missing / action |
|---|---|---|---|---|
| Python + FastAPI | `app/main.py`, `app/api/routes/` | Test suite; live stack | Implemented | — |
| Any LLM API | `app/services/llm/openai_compat.py` (OpenAI-compatible HTTP), `mock.py` | Adapter: stubbed HTTP tests. Mock: all tests | **Partial** | No live provider call was made. Action: add a key and run `python scripts/verify_llm.py` |
| Docker | `Dockerfile` | Built and run; uid 10001 | Implemented | — |
| Redis | `app/services/rate_limiter.py`, `cache.py` | Unit tests; integration test on real Redis | Implemented | — |
| PostgreSQL or another database | Qdrant: `app/repositories/`, `app/database/` | Integration test on real Qdrant; restart persistence check | Implemented with **another database** | PostgreSQL is not used. See section 3 |
| Optional: vector database for RAG | `app/services/rag/`, `documents` collection | API tests; smoke test shows a grounded answer with sources | Implemented | Default embedder is lexical; real embedding adapter unverified live |
| `POST /auth/login` | `app/api/routes/auth.py`, `app/services/auth_service.py` | `tests/api/test_auth_api.py` | Implemented | — |
| `POST /chat` | `app/api/routes/chat.py`, `app/services/chat_service.py` | `tests/api/test_chat_api.py` | Implemented | — |
| `GET /health` | `app/api/routes/ops.py` | `tests/api/test_ops_api.py`; live | Implemented | — |
| `GET /metrics` | `app/api/routes/ops.py`, `app/monitoring/metrics.py` | Tests; live | Implemented | ADMIN token required |

### 2.2 `/chat` requirements

| Requirement | Implementation | Verification | Status |
|---|---|---|---|
| Accept a user question | `ChatRequest` in `app/schemas/chat.py` | Validation tests | Implemented |
| Authenticate the user | `get_current_user`, `require_role` in `app/api/deps.py` | Six 401 cases; role matrix | Implemented |
| Send the question to an LLM | `LLMGateway.generate` | Mock: tests. Real provider: unverified | **Partial** |
| Return the generated answer | `ChatResponse` | Tests; smoke test | Implemented |
| Handle LLM timeout/errors | Error classes in `app/services/llm/base.py`; mapping in `chat_service.py` | Tests for timeout, 5xx, 429, auth error, malformed output | Implemented |
| Basic retry/fallback logic | `app/services/llm/gateway.py`, `circuit_breaker.py` | 17 deterministic unit tests; API tests | Implemented |
| Record request latency | `latency_ms` in response and record; `http_request_duration_seconds`, `llm_request_duration_seconds` | Tests; `/metrics` | Implemented |
| Record LLM token usage | `usage` in response; stored per record; `llm_tokens_total` | Tests | Implemented. Real provider counts unverified; mock counts are simulated |
| Return appropriate HTTP errors | One envelope; 401/403/413/422/429/502/503/504 | Tests assert status, code and absence of internals | Implemented |

### 2.3 Authentication and authorisation

| Requirement | Implementation | Verification | Status |
|---|---|---|---|
| Basic JWT authentication | `app/core/security.py` | Expiry, tamper, wrong secret, `alg=none`, missing claims | Implemented |
| Explain extension to SSO/OIDC | [architecture.md §6](architecture.md), [technical-report.md §6.5](technical-report.md) | — | Documented only (as asked) |
| Explain RBAC and role differences | Implemented for three roles; explained in README §5 and report §6 | `test_rbac_matrix`: 12 endpoints × 3 roles | Implemented and documented |

### 2.4 Docker and deployment

| Requirement | Implementation | Verification | Status |
|---|---|---|---|
| Containerise with Docker | `Dockerfile` (multi-stage, non-root) | Built; smoke test | Implemented |
| Docker Compose **or** Kubernetes manifests | `docker-compose.yml` (and `k8s/` in addition) | Compose: run from a fresh clone. Kubernetes: YAML parse only | Compose implemented; Kubernetes **partial** (never run) |
| Architecture: Users → LB → FastAPI instances → Redis/Queue → LLM Gateway → LLM APIs | nginx → 3 replicas → Redis → gateway module → provider | Smoke test shows three replicas answering | Implemented, **except the queue** (documented design only) |
| PostgreSQL where appropriate for persistent data | Qdrant used instead | — | **Deviation** — section 3 |
| Dockerfile in repository | Yes | — | Implemented |
| Environment-based configuration | `app/core/config.py`, `.env.example` | Config tests; fresh-clone run | Implemented |
| No hard-coded secrets/API keys | All from environment; `.env` ignored | History scan, section 5.4 | Implemented |
| Setup instructions in README | `README.md` §4 | Followed on a fresh clone | Implemented |

### 2.5 Scaling scenario (explanation required)

| Topic | Where | Status |
|---|---|---|
| Horizontal scaling | [scaling-analysis.md §4](scaling-analysis.md) | Documented; demonstrated locally with 3 replicas |
| Load balancing and health checks | §5 | Documented; nginx implemented |
| Kubernetes HPA | §6; `k8s/app.yaml` | Documented; manifest never run |
| Redis caching / distributed rate limiting | §7, §9 | Implemented and documented |
| Background queues | §8 | **Documented only** — not implemented |
| Rate limiting | §7 | Implemented and documented |
| LLM API limits (RPM, TPM, concurrency) | §2 | Documented with stated assumptions; no provider figures invented |
| Concurrent requests | §2, §7, §12 | Implemented (semaphore, shedding); measured locally |
| Failure recovery | §11, §14 | Implemented (retry, timeout, fallback, degradation); recovery objectives not measured |
| Simple architecture diagram | README §2, architecture.md §3, scaling-analysis.md §13 | Provided |

### 2.6 Architecture and migration question (explanation required)

All nine sub-questions are answered in [migration-plan.md](migration-plan.md) and
[scaling-analysis.md](scaling-analysis.md): how to scale; LLM API limits; slow or failing
requests; where Redis and queues are used; retries, timeouts and fallbacks; monitoring; failure
handling; minimal-downtime migration; secrets and configuration. Status: **documented only**,
which is what the assessment asks for. Nothing in it was executed.

### 2.7 Expected submission

| Item | Status | Action |
|---|---|---|
| FastAPI application | Implemented | — |
| JWT authentication | Implemented | — |
| `/chat` with LLM integration | Implemented with mock; real provider **partial** | Run `verify_llm.py` with a key if one is available |
| Redis integration | Implemented | — |
| Database integration | Implemented (Qdrant) | Be ready to defend the choice |
| Docker configuration | Implemented | — |
| Error handling and retries | Implemented | — |
| Basic tests | Implemented (150) | — |
| README.md | Implemented; verified by fresh clone | — |
| Architecture diagram | Implemented (Mermaid, renders on GitHub) | — |
| Git repository | Local repository with 11+ commits | **Student: create the GitHub repository and push** |
| Loom / voice-over video, max 5 minutes | Script written and every command rehearsed | **Student: record it** |

## 3. Database architecture review

**Finding.** The assessment says "PostgreSQL or another database" in the core task, and
"PostgreSQL should be used where appropriate for persistent application data" under deployment.
The project uses only Qdrant. The first sentence permits this; the second expresses a preference
it does not follow. This is the single largest compliance risk in the submission.

| Criterion | Qdrant only (current) | PostgreSQL + Qdrant | PostgreSQL + `pgvector` |
|---|---|---|---|
| Transactional integrity | None | ACID for application data | ACID for everything |
| Relational queries | Filter + sort within one collection | Full SQL | Full SQL, joins with vector results |
| Persistence | Volume; no backup procedure | Mature backup, point-in-time recovery | Same, one procedure |
| Auditability | Mutable points | Append-only tables, constraints | Same |
| Vector search | Purpose-built, scales out | Same | Adequate for modest corpora |
| Operational complexity | 2 data services | 3 data services | 2 data services |
| RAG requirement | Met | Met | Met |

**Recommendation.** For a production system: PostgreSQL as the system of record for users, chat
and usage records and audit events; vectors in `pgvector` while the corpus is modest, or Qdrant
when it grows. For this submission: **keep the current implementation** — it works, is tested,
and was chosen deliberately — and present the deviation openly.

**Minimum changes for compliance.** None are strictly required. If the evaluator insists on
PostgreSQL, the smallest change is to re-implement `app/repositories/users.py` and
`app/repositories/chats.py` on PostgreSQL (SQLAlchemy + Alembic), keep
`app/repositories/documents.py` on Qdrant, and add one Compose service. Services, routes and
tests above the repository layer would not change. This was not done, to avoid rewriting a
working system days before submission.

## 4. Real LLM verification

**Limitation: no real LLM request has been made.** No API key was available. Every statement
about real-provider behaviour is derived from tests against stubbed HTTP responses.

### 4.1 What is verified without a key

| Aspect | Verified by |
|---|---|
| Request schema: URL `/chat/completions`, bearer header, `model`, system + user messages, `temperature`, token cap | `test_openai_adapter_success_and_request_shape` |
| Response parsing: `choices[0].message.content`, provider's `model`, `usage` | same |
| Usage is `null` when the provider omits it | `test_openai_adapter_usage_is_null_when_not_reported` |
| 401/403 → auth error; 429 → rate-limit error with `Retry-After`; 5xx → server error; 400 → bad request; empty or malformed body → content error | `test_openai_adapter_error_classification` (9 cases) |
| Timeout and connection failure | `test_openai_adapter_network_failures` |
| Missing key → safe 503, `/health` degraded | `test_unconfigured_real_provider_is_a_safe_503`; `scripts/verify_llm.py` exits 2 and sends nothing |
| Retry limits, fallback, breaker | `tests/unit/test_gateway.py` |

### 4.2 Procedure to verify one real request

1. Obtain a key from any provider with an OpenAI-compatible endpoint. Read the base URL and a
   current model name from that provider's documentation.
2. Put them in `.env` only — never in chat, a commit, a screenshot or the video:

   ```
   LLM_PROVIDER=openai_compatible
   OPENAI_BASE_URL=<from the provider's documentation>
   OPENAI_API_KEY=<the key>
   OPENAI_MODEL=<from the provider's documentation>
   LLM_FALLBACK_PROVIDER=mock
   ```

3. Run `python scripts/verify_llm.py`. It sends one short real request and then checks an
   invalid key (auth error, no retry, fallback answers) and a 1 ms timeout (timeout error after
   exactly two retries). It prints the model, latency and token counts, and never the key.
4. Run `docker compose up -d`, then call `/health` (expect `"llm": "configured"`) and `/chat`
   (expect `"provider": "openai_compatible"` and non-null `usage`).
5. Paste the script's output into `docs/evidence/verify-llm.txt` and change the status of the
   adapter in the README and report from "unverified" to "verified with <provider>".
6. If any request field is rejected (some models require `max_completion_tokens`), set
   `OPENAI_MAX_TOKENS_PARAM` accordingly and record that.

Cost: three short requests of a few dozen tokens.

## 5. Security audit

### 5.1 Findings and actions

| # | Area | Finding | Severity | Action taken |
|---|---|---|---|---|
| 1 | Health | Readiness returned 503 when Redis was down, although `/chat` is designed to keep working without Redis. A load balancer honouring it would have removed every replica | High (availability) | **Fixed**: readiness gates on Qdrant only; test updated; verified live |
| 2 | Tokens | A password change left previously issued tokens valid | Medium | **Fixed**: tokens issued before `password_changed_ts` are rejected; test added |
| 3 | Audit | Knowledge-base changes were not audited, and no endpoint could read the audit trail | Medium | **Fixed**: `document.ingest` / `document.delete` events; `GET /admin/audit` (ADMIN); test added |
| 4 | Errors | nginx answered oversized bodies with its HTML error page | Low | **Fixed**: same JSON envelope; verified with a 400 kB body |
| 5 | Exposure | Swagger UI is served without authentication in every environment | Low | `DOCS_ENABLED=false` now hides it; default left on for the demonstration |
| 6 | Code quality | Type checker had never been run | Low | **Fixed**: 14 findings corrected; `mypy` added to the CI workflow |
| 7 | Admin account | Is there a default password? | — | **No.** `.env.example` leaves `ADMIN_PASSWORD` empty; the init job refuses to seed without one and rejects a weak one; `scripts/make_env.py` generates a random value that is written only to `.env` |
| 8 | Data stores | Redis and Qdrant have no authentication inside the Compose network | Medium | Not changed. Neither publishes a host port. Documented as a limitation |
| 9 | Transport | No TLS locally | Medium for production | Not changed. Documented; TLS belongs at the load balancer |
| 10 | Login | Throttle is per username + IP, so a distributed attack is limited only per IP | Low–Medium | Not changed. Documented |
| 11 | Tokens | A single token of an active account cannot be revoked before expiry | Low | Not changed. Documented |

### 5.2 Controls confirmed in place

JWT: algorithm pinned to HS256; `alg=none`, wrong secret, tampered payload, expired token and
missing claims all rejected; startup refuses a weak secret in `prod`. Passwords: Argon2id, per-
password salt, never returned or logged. Roles: deny by default, read from the database, matrix
tested. Rate limiting: atomic and shared by replicas (proved on real Redis). Input: length,
type and unknown-field checks; values never echoed in errors. Logging: no content, credentials
or tokens; redaction filter. Prompt injection: fixed system prompt, delimited untrusted input,
no tools or secrets available to the model — with the stated caveat that it cannot be fully
prevented. Docker: multi-stage, slim base, uid 10001, no published database ports.

### 5.3 Dependencies

`pip-audit -r requirements.txt`: "No known vulnerabilities found" (twice, including from a fresh
virtual environment). This is a point-in-time result. The container image was not scanned.

### 5.4 Git history

| Check | Result |
|---|---|
| Tracked files matching `.env`, keys, databases | Only `k8s/secret.example.yaml`, a template with `REPLACE_ME` placeholders |
| `git check-ignore .env` | Ignored by `.gitignore` line 2 |
| Pattern scan of `git log -p --all` for API-key, AWS-key, JWT and private-key shapes and for `SECRET=value` assignments | Two matches, both the deliberately fake strings in the log-redaction unit test |
| Search of history and working tree for the **actual** `JWT_SECRET` and `ADMIN_PASSWORD` values from `.env` | Not present anywhere except `.env` |
| Dedicated scanner (gitleaks) | **Not run**: not installed |

Conclusion: no real secret is in the repository or its history. Before pushing, re-run
`git status` and confirm `.env` is not listed.

## 6. Testing and benchmark audit

Tests: section 1. The suite needs no external service, which is why it reproduces exactly.

Benchmarks: the documentation distinguishes five things, and the audit confirmed each is stated
correctly.

| Distinction | How it is kept |
|---|---|
| Mock LLM latency | `MOCK_LATENCY_SECONDS` is an artificial sleep; runs 1–3 are labelled "simulated 1 s" |
| Real provider latency | **Never measured.** Stated in every document that quotes a number |
| Application throughput | Run 5: one replica saturates near 72 req/s with zero model latency |
| Client-side bottleneck | Run 4: client median 273–298 ms versus nginx median 25–26 ms; the figure is labelled a lower bound |
| Server-side timing | nginx `request_time` is recorded for runs through nginx |

No document claims 500 req/s. Remaining weaknesses of the benchmark: a single-process generator,
short runs (10–40 seconds), one machine shared by generator and system under test, and no
warm-up discipline.

## 7. README and repository review

Performed on a **fresh clone in a new folder**, using only the README:

| Step | Result |
|---|---|
| `python scripts/make_env.py` | `.env` created with random secrets |
| `docker compose up --build -d` (separate project name and port, to coexist with the main stack) | All services healthy |
| `python scripts/smoke_test.py` | 21/21 |
| README login, document, chat and metrics examples | Returned the documented shapes |
| New virtual environment, `pip install -r requirements-dev.txt`, `pytest`, `ruff`, `mypy`, `pip-audit` | 150 passed; all clean |

Corrections made to the README during the audit: test count; readiness semantics; new audit
endpoint; password-change behaviour; type-check command; the example response replaced with one
captured from the running stack; the live-provider verification procedure.

Known README limitation: the `curl` examples assume a bash-style shell. On Windows PowerShell use
`curl.exe`, the Swagger UI, or the commands in [demo-script.md](demo-script.md), which were
rehearsed in PowerShell.

## 8. Open items for the student

1. Push to GitHub and confirm the Actions workflow passes (it has never run).
2. Record the video.
3. Optional but valuable: verify one real LLM request (section 4.2).
4. Decide whether the `Co-Authored-By` trailer in the commit messages is acceptable for the
   submission.
5. Add the two missing references in the technical report.
6. Be ready to defend the database decision (section 3).
