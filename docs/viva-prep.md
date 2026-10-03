# Viva Preparation

Short, defensible answers tied to this repository. Each answer names the file that proves it. "Follow-up trap" lines are the questions an examiner is likely to ask next, with the honest answer.

Status labels used throughout the project: **[IMPLEMENTED]** built, run and tested here; **[CONFIGURED]** files exist but were never run (the Kubernetes manifests, parsed as YAML only); **[PROPOSED]** design only (everything about AWS, OIDC, queues, token revocation).

Three facts to state before anyone asks: no real LLM provider was ever called (mock only; the OpenAI-compatible adapter is tested against stubbed HTTP), nothing was deployed to a cloud, and 500 RPS was not tested.

See also: [technical report](technical-report.md), [demo script](demo-script.md), [evidence](evidence/).

---

## Part A. Questions and answers

### 1. Why FastAPI rather than Flask or Django?

The workload is I/O-bound: a request spends almost all of its time waiting for the LLM, Redis or Qdrant. FastAPI is async-native, so one process can hold many waiting requests on a single event loop. Its dependency injection is what implements authentication and RBAC here (`get_current_user` and `require_role` in `app/api/deps.py`), and the Pydantic models in `app/schemas/` give validation and the Swagger UI from the same definitions. Flask is synchronous by default, so each waiting request would occupy a worker. Django brings an ORM and admin built around a relational database, which this project does not have.

**Follow-up trap:** "Is FastAPI faster for CPU work?" No. Async helps waiting, not computing. One replica saturated at 72.1 req/s in load run 5 because a single Python event loop was doing the CPU work.

### 2. Why Redis, and what breaks without it when there are several replicas?

Replicas share nothing in memory. Without Redis, a rate-limit counter kept in each process would give every user three times the limit with three replicas, a login lockout would apply on one replica only, and each replica would have its own cache. Redis holds the state all replicas must agree on: the chat rate limit, the login throttle, the response cache, the knowledge-base version counter and the user-creation lock (`app/services/rate_limiter.py`, `cache.py`, `rag/knowledge_base.py`, `auth_service.py`). The smoke test shows a 429 after exactly 20 requests even though requests were spread over three replicas.

**Follow-up trap:** "What happens when Redis is down?" Chat limiter fails open with a per-process cap, the cache is treated as a miss, and login fails closed with 503. This was tested automatically and by stopping the Redis container: `/health` degraded, `/health/ready` and `/health/live` still 200.

### 3. Why a vector database instead of PostgreSQL? When would PostgreSQL be better?

The assessment allows "PostgreSQL or another database". RAG needs a vector index in any case, and the remaining access patterns are narrow: fetch a user by ID, append a chat record, list records by user ordered by time. Qdrant covers those with retrieve, upsert and filtered ordered scroll, so one datastore serves both roles. The price is real: no ACID transactions, no unique constraints, no joins and no SQL. Username uniqueness comes from a deterministic UUIDv5 point ID plus a Redis `SET NX` lock (`app/repositories/users.py`, `UserService.create`), and pagination reads `limit + offset` and slices. PostgreSQL would be the better, conventional choice as soon as the product needs billing, reporting, relational integrity or multi-record transactions; with pgvector it could even hold the vectors.

**Follow-up trap:** "So is this the right choice for production?" For user and audit data, PostgreSQL is safer. The repository layer is the only code that would change, and that migration is on the roadmap.

### 4. What is RAG, and how does retrieval work here?

Retrieval-augmented generation means fetching relevant text first and giving it to the model as context, so the answer is grounded in the organisation's documents rather than only the model's training data. Here an ADMIN posts a document; `chunk_text` splits it into chunks of at most 800 characters; each chunk is embedded and stored in the Qdrant `documents` collection. On `/chat`, the question is embedded with the same embedder, Qdrant returns the top 4 chunks by cosine similarity above 0.08, and those chunks go into the prompt inside `<context>` delimiters. The response lists them as `sources`.

**Follow-up trap:** "What if nothing is retrieved or retrieval fails?" The LLM is called without context. A retrieval error is counted in `rag_retrievals_total{outcome="error"}` and does not fail the request.

### 5. What is an embedding, and why cosine similarity?

An embedding is a fixed-length vector of numbers that represents a text, built so that similar texts have vectors pointing in similar directions. Cosine similarity measures the angle between two vectors and ignores their length, so a long chunk and a short question can still match. The vectors here are L2-normalised, in which case cosine similarity equals the dot product. The collection is created with `Distance.COSINE` and size 2048 in `app/database/bootstrap.py`.

**Follow-up trap:** "Can you mix embeddings from two models?" No. Different models produce incomparable spaces. `ensure_collections` raises `SchemaMismatchError` if the dimension differs, and documents must be re-ingested.

### 6. What are the limits of the hash embedder?

`HashEmbedder` in `app/services/rag/embeddings.py` is the hashing trick over words: each distinct word is hashed into one of 2048 buckets with a sign. It is lexical, not semantic. Texts match only if they share words, so "car" and "automobile" are unrelated, and hash collisions add noise. It exists so that the pipeline runs offline, free and deterministically in tests. `OpenAICompatibleEmbedder` is implemented for real semantic embeddings but was tested only against stubbed HTTP.

**Follow-up trap:** "Then is your RAG demo meaningful?" It demonstrates the pipeline (ingest, index, retrieve, cite, invalidate cache), not retrieval quality. Quality was not evaluated.

### 7. Why JWT? How does it compare with server-side sessions? What about revocation?

A JWT is a signed token the server can verify without looking up a session, so any replica can authenticate any request. Server-side sessions are easy to revoke (delete the session) but need a shared session store on every request. This project is a hybrid: the JWT proves identity, but `get_current_user` reloads the user from Qdrant on every request, so deactivating an account or changing a role takes effect immediately (`test_deactivated_user_token_stops_working_immediately`). A password change also invalidates every token issued before it (`password_changed_ts` is compared with the token's `iat`; `test_password_change_invalidates_existing_tokens`). What cannot be done is revoking one specific token for an active account before its 30-minute expiry.

**Follow-up trap:** "If you read the database on every request, why use JWT at all?" Fair point: the benefit left is that no session store is needed and the token is self-verifying. A `jti` denylist in Redis or refresh tokens would add revocation; both are [PROPOSED].

**Follow-up trap:** "Why HS256?" It is simple for a single service. The weakness is that the secret that verifies can also sign. With an identity provider the design moves to RS256 or ES256 and JWKS. The algorithm is pinned in `decode_access_token`, so `alg=none` is rejected (`test_alg_none_token_rejected`).

### 8. Authentication versus authorisation? What is RBAC, and where does it fall short of ABAC?

Authentication answers "who are you?" (401 when it fails); authorisation answers "may you do this?" (403 when it fails). RBAC grants permissions to roles and assigns roles to users: here `require_role(Role.ADMIN, Role.USER)` on `/chat` and `require_role(Role.ADMIN)` on admin and ingest routes, with deny by default. The matrix is asserted cell by cell in `tests/api/test_auth_api.py`. RBAC cannot express rules that depend on attributes of the resource or the context, such as "users may read only documents of their own department" or "only during office hours"; that is attribute-based access control (ABAC). The one ownership rule here (a user reads only their own history unless ADMIN) is written by hand in `app/api/routes/chat.py`.

**Follow-up trap:** "Is the role taken from the token?" No. The token carries a `role` claim, but authorisation uses the role stored in the database (`test_role_comes_from_database_not_from_token`).

### 9. Sync versus async. What blocks the event loop?

An async server runs one event loop per process. While a coroutine awaits I/O, the loop serves other requests; if a coroutine computes or makes a blocking call without awaiting, every other request in that process waits. Argon2 is deliberately CPU- and memory-heavy, so `hash_password` and `verify_password` are run with `asyncio.to_thread` in `app/services/auth_service.py`. All network calls use async clients (httpx, redis.asyncio, AsyncQdrantClient).

**Follow-up trap:** "Is anything still blocking?" Yes: the hash embedder is pure Python on the event loop. It is negligible for a question, but ingesting a 200,000-character document embeds roughly 250 chunks inline. Moving ingestion to a worker is [PROPOSED].

### 10. Why Argon2 and not SHA-256? What is a salt?

SHA-256 is designed to be fast, which lets an attacker with a stolen database try billions of guesses per second on GPUs. Argon2id is deliberately slow and memory-hard, so each guess is expensive and hard to parallelise; it is the algorithm specified in RFC 9106. A salt is a random value stored with each hash so identical passwords produce different hashes and precomputed tables are useless; argon2-cffi generates one per password and encodes it in the hash string (`test_password_hash_roundtrip_and_salting`).

**Follow-up trap:** "What about unknown usernames?" A dummy hash is verified anyway (`dummy_password_hash`), so response time does not reveal which usernames exist, and all failures return the same message.

### 11. Retries, exponential backoff, jitter, retry storms. Why not retry 400 or 401?

A retry helps only when the failure is transient: timeout, 5xx, 429. Exponential backoff doubles the wait after each failure so a struggling provider is given room. Jitter randomises the wait; without it, all clients that failed together retry together and cause a second spike (a retry storm). `LLMGateway._retry_delay` uses full jitter, `random() × min(8, 0.5 × 2^attempt)`, and honours the provider's `Retry-After` on a 429. Retries are bounded (2) and never cross the overall deadline. A 400 means the request itself is wrong, and a 401 means the key is wrong: repeating either gives the same result and costs time.

**Follow-up trap:** "Is a 401 treated the same as a 400?" Not quite. Neither is retried, but an auth error may fall back to another provider and counts toward the circuit breaker; a bad request does neither (`test_bad_request_does_not_fall_back`).

### 12. What is a circuit breaker for? What are its states?

When a provider is down, every request would otherwise wait for a timeout and retries before failing. The breaker remembers recent failures and fails fast. CLOSED: calls pass; five consecutive failures open it. OPEN: calls are rejected immediately for 30 s. HALF_OPEN: one trial call is admitted; success closes the circuit, failure reopens it. The code is `app/services/llm/circuit_breaker.py`; the state is exported as the `llm_circuit_state` gauge.

**Follow-up trap:** "Is the state shared between replicas?" No, it is per process. Each replica needs its own five failures to open. Sharing through Redis is [PROPOSED].

### 13. Timeout versus deadline?

A timeout bounds one attempt (`LLM_TIMEOUT_SECONDS`, 15 s). A deadline bounds the whole operation, including waiting for a slot, every retry, every backoff and the fallback (`LLM_OVERALL_DEADLINE_SECONDS`, 40 s). Without a deadline, three attempts of 15 s plus backoff could exceed what the client or the proxy will wait. In `gateway.py` each attempt's timeout is `min(timeout, time remaining)`, and no retry starts if its delay would cross the deadline. nginx's `proxy_read_timeout` is 60 s, above the deadline.

**Follow-up trap:** "What does the client receive?" 504 `LLM_TIMEOUT` with a generic message; the detail is in the logs under the same request ID.

### 14. Rate-limiting algorithms, and why Redis atomicity matters

Fixed window counts requests per clock window; it is one counter and one operation, but a burst straddling a boundary can reach twice the limit. Sliding window (log or weighted counters) removes that at the cost of more state. Token bucket refills tokens at a steady rate and allows controlled bursts. This project uses a fixed window: key `rl:chat:{user}:{window}`, with `INCR` and `EXPIRE` sent in one MULTI/EXEC (`RateLimiter.hit`). Atomicity matters because a read-then-write sequence would let two replicas both read 19 and both admit request 20; `INCR` returns a unique count to each caller.

**Follow-up trap:** "How do you know it is atomic in practice?" The integration test sends 50 concurrent hits from two separate clients to real Redis 7.4 with a limit of 20 and asserts that exactly 20 are allowed.

**Follow-up trap:** "Why MULTI/EXEC around INCR and EXPIRE?" So a key can never be left without a TTL if the process dies between the two commands.

### 15. Cache key design, privacy risk of a shared cache, and invalidation

The key is a SHA-256 over user ID, normalised question, provider, model, temperature, prompt version, the RAG flag and the knowledge-base version (`build_cache_key` in `app/services/cache.py`). Anything that can change the answer must be in the key. The user ID is included because a shared cache could serve one user's answer, possibly based on something personal in their question, to another user; the cost is a lower hit rate. Invalidation is by version: every ingest or delete increments `kb:version`, so old entries become unreachable and expire by TTL (600 s). Only successful, non-fallback answers are cached.

**Follow-up trap:** "Does a cache hit bypass the rate limit?" No. The limiter runs first, so hits still count, and a chat record is still written with `cached: true`.

### 16. Liveness versus readiness versus health

Liveness (`/health/live`) asks whether the process is running; it checks no dependency, so a database outage does not cause healthy processes to be restarted. Readiness (`/health/ready`) asks whether traffic should be sent here; it returns 503 unless Qdrant answers with all four collections. Redis is reported in the body but does not gate readiness. `/health` is the view for people: `ok`, `degraded` (Redis down or LLM not configured, HTTP 200) or `unhealthy` (Qdrant down, 503). The code is in `app/api/routes/ops.py`.

**Follow-up trap:** "Why is Redis not part of readiness?" Because chat is designed to keep working without Redis (the limiter fails open, the cache is skipped). If readiness failed on Redis, a load balancer would remove every replica at the same moment and turn a degraded service into a full outage. An earlier version did gate on Redis; the final audit found that it contradicted the fail-open design and changed it. The Redis outage is still visible in `/health` and in the `dependency_up` metric.

### 17. Connection pooling, and why replicas × pool size matters

Opening a TCP connection per request is slow, so clients keep a pool. Each process creates one `AsyncQdrantClient` (pooled HTTP connections), one Redis client (connection pool) and one httpx client per provider, all in `app/container.py`, shared by every request. The total number of connections a datastore sees is replicas multiplied by the per-replica pool, so autoscaling the API tier multiplies connections to Redis and Qdrant. With a relational database this is the classic reason for a connection pooler; here it means checking the datastore's connection limits before raising the replica count.

**Follow-up trap:** "What pool sizes did you set?" The library defaults; they were not tuned or measured.

### 18. Horizontal versus vertical scaling. What makes a service stateless?

Vertical scaling uses a bigger machine: simple, but limited and still a single point of failure. Horizontal scaling adds identical instances behind a load balancer, which requires that any instance can serve any request. The API keeps no per-user state in memory: identity is in the token, shared counters and cache are in Redis, data is in Qdrant, and schema creation happens once in the `init` job. Compose runs three replicas, and the smoke test saw three distinct `X-Served-By` values.

**Follow-up trap:** "Is anything per-process?" Yes: the circuit breaker, the LLM concurrency semaphore, Prometheus counters and the fallback in-process limiter. None affects correctness, but fleet-wide LLM concurrency is `replicas × 20`.

### 19. Why can the system not simply "support 500 RPS"?

Because the bottleneck is the LLM provider, not the web tier. Little's Law gives in-flight requests = arrival rate × time in system. Assuming 5 s per answer, 500 RPS means 2,500 concurrent provider calls; at 20 per replica that is 125 replicas, and the provider must accept 30,000 requests per minute. Assuming 1,000 tokens per request, that is 30,000,000 tokens per minute, which must be compared with the provider's published limits; those must be looked up and are not claimed here. The local measurements match the model: with 1 s mock latency, one replica with 20 slots gave 19.2 req/s and three replicas gave 53.0 req/s (limit 60). With zero mock latency three replicas gave 118.5 req/s, which is a lower bound because the load generator was the bottleneck.

**Follow-up trap:** "So what is your system's maximum throughput?" Unknown. It was not measured to saturation behind nginx, and never with a real model. One replica alone saturated at 72.1 req/s with zero simulated latency on a laptop.

### 20. Docker versus a VM; multi-stage builds; non-root; why Compose is not production HA

A VM virtualises hardware and runs its own kernel; a container is an isolated process sharing the host kernel, so it starts faster and is smaller but isolates less strongly. The multi-stage `Dockerfile` installs dependencies in a builder stage and copies only the virtual environment and `app/` into the runtime stage. The process runs as uid 10001, so a compromise does not give root in the container. Compose runs everything on one host: if the host fails, everything fails, and Qdrant and Redis are single instances with no failover.

**Follow-up trap:** "Is the root filesystem read-only?" Not under Compose. It is set in the Kubernetes manifest, which is [CONFIGURED] only.

### 21. Kubernetes HPA versus ECS autoscaling

Both change the number of running copies based on a metric. The Kubernetes HorizontalPodAutoscaler adjusts Deployment replicas from CPU, memory or custom metrics; `k8s/app.yaml` defines one from 3 to 30 pods on 60% CPU, with fast scale-up and slow scale-down. ECS Service Auto Scaling does the same for tasks using target tracking or step policies on CloudWatch metrics such as CPU or requests per target. For an LLM proxy, CPU is a weak signal because tasks mostly wait; in-flight requests per replica is better.

**Follow-up trap:** "Did you run the HPA?" No. The manifests were parsed as YAML only; no cluster was available. Autoscaling also raises total provider concurrency, so it needs a global limiter.

### 22. Prompt injection: mitigations and their limits

Prompt injection is text that tries to make the model ignore its instructions. Direct injection comes in the question; indirect injection comes from a retrieved document. Mitigations in `app/services/llm/base.py`: the system prompt is fixed on the server; user text goes only in the user message inside `<question>` delimiters; retrieved text goes inside `<context>` and is declared untrusted reference data; only ADMIN can ingest documents; answers cite sources; the model has no tools and sees no secrets, so the worst outcome is a wrong or manipulated answer, not an action. These reduce risk; they do not eliminate it, because a model can still follow injected text.

**Follow-up trap:** "What if an admin ingests a poisoned document?" Then every user whose question retrieves it is exposed. Content review at ingestion and per-document access control are [PROPOSED].

**Follow-up trap:** "Did you test injection against a real model?" No. Only that the prompt is built with the delimiters (`test_prompt_keeps_user_text_inside_delimiters`).

### 23. OAuth2/OIDC flow, and how this application would migrate

OAuth2 is a framework for delegated authorisation; OIDC adds an identity layer (an ID token and a user-info endpoint). In the Authorization Code flow with PKCE, the client redirects the user to the identity provider, the user authenticates there, the client receives a code and exchanges it (with the PKCE verifier) for tokens, and then calls the API with the access token. To migrate, the API stops issuing tokens, verifies the provider's RS256 or ES256 signature using keys from its JWKS endpoint, checks `iss`, `aud` and `exp`, and maps a groups or roles claim to `Role`. `require_role` stays the same; `/auth/login` and password storage are retired. All of this is [PROPOSED].

**Follow-up trap:** "What do you gain?" SSO, MFA, central revocation and no signing secret inside the API.

### 24. Migrating from a single EC2 instance with minimal downtime

All [PROPOSED]. Phase 0: make the instance reproducible (image in a registry, secrets in a manager, Qdrant snapshots to object storage, baseline metrics). Phase 1: move state out (managed Redis, Qdrant on its own node or managed), switching by changing two URLs. Phase 2: put a load balancer with TLS in front and add a second instance in another zone, health-checked on `/health/ready`. Phase 3: move to ECS or EKS with rolling deploys and autoscaling, shifting traffic by weights. Phase 4: queue, global limiter, second provider, WAF. Each phase is reversible, and the old path stays up until the new one has served traffic.

**Follow-up trap:** "Where is downtime unavoidable?" Moving Qdrant: writes must pause between the final snapshot and the switch, or recent data is lost.

### 25. What would you do with another month?

In order: test against one real provider with a spend cap and record real latency and token use; replace the hash embedder with real embeddings and measure retrieval quality; run the Kubernetes manifests on a local cluster; add Qdrant snapshots and rehearse a restore; move ingestion to a background queue; add a global concurrency limiter in Redis; add token revocation or move to OIDC; add image and secret scanning to CI; and deploy phases 0 to 2 of the migration plan.

### 26. What are the weakest parts of your project?

1. No real LLM was ever called, so latency, token usage and provider error handling are unverified in practice.
2. Qdrant is the system of record without transactions, constraints or backups.
3. The default embedder is lexical; retrieval quality was not evaluated.
4. Everything ran on one laptop; the highest throughput figure is limited by the load generator.
5. Kubernetes manifests were never run; they were only parsed as YAML.
6. A single token cannot be revoked; HS256 shared secret; no TLS locally.
7. Per-process breaker and semaphore; `/metrics` through nginx shows one replica.

Stating these first is better than having them discovered.

### 27. Walk me through a `/chat` request from socket to database row

1. The client sends `POST /chat` to nginx on port 8000. nginx rejects bodies over 300k, picks a replica by round robin, overwrites `X-Real-IP` and proxies over a kept-alive connection (`docker/nginx.conf`).
2. In the replica, the `request_context` middleware in `app/main.py` accepts or generates a request ID, stores it in a `ContextVar` for logging, checks `Content-Length` against `MAX_BODY_BYTES`, and starts a timer.
3. FastAPI validates the body into `ChatRequest` (question 1–4,000 characters, no extra fields) and resolves the dependency `require_role(Role.ADMIN, Role.USER)`.
4. `require_role` depends on `get_current_user`: `decode_access_token` verifies the HS256 signature, expiry and required claims; `UserRepository.get_by_id` loads the user from Qdrant; an inactive or missing user gives 401; a role not in the list gives 403.
5. The route calls `ChatService.ask`. It checks the model against the allowlist, then calls `ChatRateLimiter.check`, which runs `INCR` + `EXPIRE` in Redis and raises 429 with `Retry-After` when over the limit.
6. `_cache_key` reads `kb:version` and builds the SHA-256 key; `ResponseCache.get` looks it up. On a hit the response is built with `cached: true`, persisted and returned.
7. On a miss, `_retrieve` calls `KnowledgeBase.search`: the embedder turns the question into a vector, and `DocumentRepository.search` calls Qdrant `query_points` with top-k 4 and score threshold 0.08.
8. `LLMGateway.generate` fixes the deadline, acquires a semaphore slot (waiting at most 5 s), then `_call_with_retries` → `_attempt`: the breaker is consulted and `provider.generate` runs under `asyncio.wait_for`. The provider builds the messages with `SYSTEM_PROMPT` and `build_user_message`.
9. `ChatService._persist` builds a `ChatRecord` and `ChatRepository.add` upserts it as a point in the Qdrant `chat_records` collection, with `created_ts` for ordering. If this write fails, the answer is still returned and a metric is incremented.
10. A successful, non-fallback answer is stored with `ResponseCache.set` (TTL 600 s).
11. Back in the middleware: metrics are recorded with the route template, `X-Request-ID`, `X-Served-By` and security headers are added, one JSON access line is logged, and the response returns through nginx to the client.

**Follow-up trap:** "How many backend calls is that?" Uncached: three to Qdrant (user, search, record) and four round trips to Redis (limiter, version, cache get, cache set).

---

## Part B. Live-demo failure playbook

| Problem | Symptom | Immediate action | What to say |
|---|---|---|---|
| Docker Desktop not running or stack down | `curl.exe` cannot connect; `docker compose ps` is empty | `docker compose up -d` and wait for nginx; check `docker compose ps`; if the `init` job failed, show `docker compose logs init` | "The stack starts in dependency order: datastores, then the init job, then the replicas, then nginx." |
| Stack will not start at all | Build or port error | Switch to the automated tests: `pytest -q` needs no Docker (Qdrant in-memory, fakeredis, mock LLM). Then show `docs/evidence/smoke-test.txt` | "The tests exercise the same application through the ASGI interface; this file is the recorded smoke run against the live stack." |
| Port 8000 already in use | nginx fails to bind | Set `HOST_PORT=8080` in `.env`, `docker compose up -d`, use the new port | "Only nginx publishes a port, and it is configurable." |
| Login returns 503 | Redis is not healthy | `docker compose ps redis`; `docker compose start redis`; retry after a few seconds | "This is the fail-closed login policy working as designed." |
| Login returns 429 | Throttle triggered by earlier wrong passwords | Wait for `Retry-After`, or use another pre-created user | "Five failures per username and IP lock the pair for 300 seconds." |
| `/chat` returns 429 too early | The demo user used up the window during rehearsal | Wait up to 60 s, or use a second pre-created USER | "The limit is 20 per user per minute, shared across replicas." |
| Token expired mid-demo | 401 `TOKEN_EXPIRED` | Log in again (tokens last 30 minutes) | "Short expiry limits the value of a stolen token." |
| Answer has no `sources` | The question shares no words with the document | Ask using the same words as the document | "The default embedder is lexical; this is its documented limit." |
| `/metrics` shows zero for a counter | nginx sent the scrape to a replica that did not serve those requests | Call `/metrics` again | "Metrics are per replica; a real Prometheus would scrape each replica directly." |
| LLM provider down | Not applicable: the demo uses the mock | If asked, show `tests/unit/test_gateway.py` and explain timeout, retry, breaker, fallback | "No real provider was called in this project; failure handling is tested with a scripted mock." |
| Network drops | Not applicable: the whole demo is local | Continue | "The stack needs no internet connection: mock LLM and offline embedder." |
| Swagger UI does not load | Browser or cache problem | Use `curl.exe` commands from the demo script | |
| Total failure | Nothing works | Play the backup recording; walk through `docs/evidence/` | State plainly that the live environment failed and that the evidence files are the recorded results. |

General rule: never improvise a feature that is not implemented. If something is not built, say "that is proposed, not implemented" and point to the report section.

---

## Part C. One-page cheat-sheet

### Numbers (all measured 2026-10-03, one laptop, mock LLM)

| Item | Value |
|---|---|
| Test machine | Intel Core i5-12500H, 16 logical CPUs, 16 GB RAM, Windows 11, Docker Desktop 29.8.1 (WSL2 VM: 16 CPUs, 7.6 GB) |
| Tests | 150 passed, 3 skipped, about 20 s |
| Coverage | 96% (1,644 statements, 62 missed) |
| Integration tests | 3 passed on real Redis 7.4 and Qdrant 1.19.1; 50 concurrent hits → exactly 20 allowed |
| pip-audit | No known vulnerabilities found |
| Ruff | check and format clean |
| Smoke test | 21 of 21; three distinct replicas; containers run as uid 10001 |
| Redis stopped | `/health` degraded (200); `/health/ready` 200 (Redis does not gate it); `/health/live` 200; back to ok within seconds of Redis returning |
| Restart | `down` then `up` kept users and chat records |
| Run 1 | 1 s latency, 3 replicas (60 slots), concurrency 100 → 53.0 req/s, all 200, client p50 1.80 s (prediction ≤ 60) |
| Run 2 | 1 s latency, one replica (20 slots) → 19.2 req/s |
| Run 3 | one replica, concurrency 300 → 300 × 200, 300 × 503 `LLM_OVERLOADED`, nothing hung |
| Run 4 | zero latency, 3 replicas, concurrency 50 → 118.5 req/s, all 200; nginx p50 0.025 s, p95 0.039 s, p99 0.117 s; client p50 273 ms → load generator was the bottleneck; lower bound |
| Run 5 | zero latency, one replica → 72.1 req/s (replica saturated) |
| Not done | No real LLM; no cloud; Kubernetes not run; 500 RPS not tested |

### Defaults worth remembering

| Setting | Value |
|---|---|
| JWT | HS256, 30 minutes, claims `sub`, `role`, `iat`, `exp`, `jti` |
| Chat rate limit | 20 per user per 60 s, fixed window |
| Login throttle | 5 failures per username + IP, 300 s |
| Cache TTL | 600 s, key includes user ID and KB version |
| LLM timeout / deadline | 15 s per attempt / 40 s overall |
| Retries | 2, backoff base 0.5 s, cap 8 s, full jitter |
| Concurrency | 20 per replica, 5 s queue wait, then 503 |
| Breaker | opens after 5 failures, trial after 30 s |
| RAG | chunk 800 characters, overlap 100, top-k 4, threshold 0.08, 2048 dimensions, cosine |
| Collections | `documents` (vectors), `users`, `chat_records`, `audit_events` (payload only) |
| Replicas | 3 (`APP_REPLICAS`) |

### Arithmetic (assumptions, not measurements)

- Little's Law: in-flight = RPS × seconds per request.
- 100 RPS × 5 s = 500 in-flight → 25 replicas at 20 each.
- 500 RPS × 5 s = 2,500 in-flight → 125 replicas at 20 each.
- At an assumed 1,000 tokens per request: 100 RPS = 6,000,000 TPM; 500 RPS = 30,000,000 TPM. Compare with the provider's published limits.

### Commands

```powershell
python scripts/make_env.py                     # once
docker compose up --build -d                   # start
docker compose ps                              # status
python scripts/smoke_test.py                   # 21 checks
pytest --cov=app --cov-report=term-missing     # tests, no Docker needed
ruff check . ; ruff format --check .
pip-audit -r requirements.txt
$env:RUN_INTEGRATION=1; pytest -m integration  # needs the dev override stack
docker compose logs -f app                     # JSON logs
docker compose stop redis                      # outage experiment
docker compose start redis
docker compose exec nginx nginx -s reload      # after changing replicas
curl.exe -s http://localhost:8000/health
```

Swagger UI: http://localhost:8000/docs
