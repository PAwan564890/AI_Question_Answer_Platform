# Code guide: how to read, explain and defend this code base

This guide is for the person who has to explain the project. Read it with the source files open.
Part 1 walks through each module. Part 2 is a set of short learning notes per concept. Part 3
lists what to study before submission.

The best way to learn the code is to trace one request. Start at `app/api/routes/chat.py`,
follow `ChatService.ask` in `app/services/chat_service.py` step by step, and open each module it
calls.

---

## Part 1 — Module by module

Each entry answers the same questions: what it does, why it exists, how it works, the important
names, what it talks to, what happens on failure, what is essential in production, and what a
smaller application could drop.

### `app/core/config.py` — settings

* **What / why:** one `Settings` class that reads every option from environment variables. It
  exists so that no other file reads the environment and no secret is written in code.
* **How:** `pydantic-settings` maps `JWT_SECRET` → `settings.jwt_secret` and checks types and
  ranges. A validator refuses to start in `prod` with a weak JWT secret.
* **Important names:** `Settings`, `get_settings()` (cached), `allowed_models`, `cors_origins`.
* **Talks to:** everything receives `settings` through `app/container.py`.
* **On failure:** an invalid value stops the process at start-up with a clear message. That is
  intended: a wrong configuration should never reach users.
* **Essential:** central config and the weak-secret check. **Could drop:** most tuning knobs.

### `app/core/security.py` — passwords and tokens

* **What / why:** hashes and verifies passwords (Argon2id) and creates and verifies JWTs.
* **How:** `hash_password` adds a random salt automatically. `decode_access_token` checks the
  signature, the expiry and required claims, and only accepts the HS256 algorithm.
* **Important names:** `hash_password`, `verify_password`, `dummy_password_hash`,
  `create_access_token`, `decode_access_token`.
* **Talks to:** `auth_service.py` (login) and `api/deps.py` (every protected request).
* **On failure:** a bad token raises `AuthenticationError`, which becomes HTTP 401.
* **Essential:** all of it. **Could drop:** nothing; this is the minimum.

### `app/core/errors.py` — error types and the error envelope

* **What / why:** defines `AppError` and its subclasses, and turns them into one JSON shape.
  It exists so that every error looks the same and none leaks internals.
* **How:** services raise, for example, `RateLimitedError(retry_after)`. One handler registered
  on the app converts any `AppError` into `{"error": {"code", "message", "request_id"}}`.
* **Important names:** `AppError`, `AuthenticationError`, `PermissionDeniedError`,
  `RateLimitedError`, `error_body`, `register_exception_handlers`.
* **Essential:** one envelope and no stack traces. **Could drop:** some subclasses.

### `app/core/logging.py` — JSON logs

* **What / why:** prints one JSON object per log line with the request id, and masks anything
  that looks like a token or key.
* **How:** a `ContextVar` holds the current request id; the formatter reads it for every line.
* **Essential:** request ids and never logging secrets. **Could drop:** the redaction patterns in
  a private prototype (not recommended).

### `app/main.py` — application factory and middleware

* **What / why:** builds the FastAPI app and installs one middleware that runs around every
  request.
* **How:** `request_context` picks a request id, calls the route through `_handle`, records
  metrics, adds headers, and writes one access-log line. `_handle` rejects oversized bodies and
  converts unexpected exceptions into a clean 500 or 503.
* **Important names:** `create_app`, `_install_request_middleware`, `_handle`,
  `_choose_request_id`, `app_factory`.
* **On failure:** any exception no route handled is logged with its stack trace and answered
  with a generic JSON error.
* **Essential:** request ids, metrics, the last-resort handler. **Could drop:** `X-Served-By`.

### `app/container.py` — wiring

* **What / why:** creates the long-lived objects once per process (Qdrant client, Redis client,
  gateway, services) and connects them.
* **How:** `build_container` accepts optional replacements, which is how tests pass in a fake
  Redis, an in-memory Qdrant and the mock provider.
* **Essential:** creating clients once and reusing them. **Could drop:** in a tiny app, global
  variables would do, at the price of harder testing.

### `app/api/deps.py` — who is calling, and are they allowed?

* **What / why:** FastAPI dependencies that authenticate the caller and check the role.
* **How:** `get_current_user` reads the bearer token, verifies it, then **loads the user from the
  database**. It rejects inactive users and tokens issued before a password change.
  `require_role(Role.ADMIN, …)` returns a dependency that raises 403 for other roles.
* **Important names:** `get_current_user`, `require_role`, `require_metrics_access`, `client_ip`.
* **On failure:** 401 (not authenticated) or 403 (authenticated but not allowed).
* **Essential:** all of it.

### `app/api/routes/` — the HTTP endpoints

* **What / why:** five small files (`auth`, `chat`, `documents`, `admin`, `ops`). A route
  validates input, checks the role, calls **one** service method and returns its result.
* **How:** request bodies are Pydantic models from `app/schemas/`, so invalid input never reaches
  a service.
* **`ops.py`:** `/health/live` checks nothing; `/health/ready` checks Qdrant; `/health` reports
  Qdrant, Redis and the LLM configuration; `/metrics` returns Prometheus text.
* **Could drop:** `admin` and `documents` routes in a minimal version.

### `app/schemas/` and `app/models/` — data shapes

* **Schemas** are what the API accepts and returns (`ChatRequest`, `ChatResponse`, `UserCreate`).
  They validate. `extra="forbid"` rejects unknown fields.
* **Models** are plain dataclasses used inside the application (`User`, `ChatRecord`, `Role`).
  They do not know about HTTP or the database.
* **Why two sets:** the public API can stay stable while internal storage changes, and
  `UserOut` simply has no password field, so a hash can never be returned by accident.

### `app/repositories/` — the only code that talks to Qdrant

* **What / why:** `users.py`, `chats.py` (chat records and audit events) and `documents.py`.
  Keeping database calls here means the database could be replaced without touching services.
* **How:** each method is one Qdrant call: `retrieve` by id, `upsert`, `scroll` with a filter and
  an order, `query_points` for vector search.
* **Worth understanding:** `user_id_for(username)` builds a UUID from the lower-cased username.
  The same name always gives the same id, which is how usernames stay unique without a database
  constraint.
* **On failure:** Qdrant errors (`ApiException`) rise to the middleware and become 503.

### `app/database/` — client, bootstrap, seed

* **`bootstrap.py`:** creates the collections and payload indexes if they are missing. Safe to
  run repeatedly. This is the project's "migration".
* **`seed.py`:** run once by the `init` container; calls the bootstrap and creates the first
  admin from `ADMIN_USERNAME` / `ADMIN_PASSWORD`. It refuses a missing or weak password.

### `app/services/auth_service.py` — login and user administration

* **`AuthService.login`:** check the lockout → load the user → verify the password in a worker
  thread → on failure count it and raise one generic error; on success issue a token.
* **`UserService`:** create (guarded by a short Redis lock), update, list. Every change writes an
  audit event that never contains a password.
* **On failure:** Redis down → login returns 503 (fail closed).

### `app/services/chat_service.py` — the heart of `/chat`

* **How:** `ask` is five commented steps: rate limit → cache lookup → retrieval → LLM call →
  save and cache. Helpers: `_resolve_model`, `_cache_key`, `_retrieve`, `_save_success`,
  `_save_failure`, `_response_from_cache`, `_response_from_llm`.
* **Worth understanding:** `_LLM_ERROR_MAP` is the single table that maps each LLM failure to an
  HTTP status and a public message.
* **On failure:** retrieval failure → answer without context. LLM failure → the failure is
  stored and a mapped error is raised. Saving fails → the answer is still returned.

### `app/services/rate_limiter.py` — limits

* **`RateLimiter.hit`:** `INCR` then `EXPIRE` in one Redis transaction, on a key that contains
  the window number.
* **`ChatRateLimiter`:** uses it; if Redis is down, falls back to `InProcessLimiter` (fail open).
* **`LoginThrottle`:** counts failed logins per username and IP; if Redis is down, refuses
  logins (fail closed).

### `app/services/cache.py` — response cache

* **`build_cache_key`:** SHA-256 over everything that can change the answer, including the user
  id. **`ResponseCache`:** `get` and `set`; any Redis error is treated as a miss.

### `app/services/llm/` — talking to the model safely

* **`base.py`:** the contract (`LLMRequest`, `LLMResult`, `LLMProvider`), the fixed system
  prompt, and the error classes. Each error class says whether it is `retryable`.
* **`mock.py`:** a fake provider. `provider.script("timeout", "ok")` makes the next call time
  out and the one after succeed, which is how failure tests work.
* **`openai_compat.py`:** one HTTP POST to `/chat/completions`. `_raise_for_status` translates
  HTTP status codes into the error classes.
* **`circuit_breaker.py`:** a small state machine: CLOSED → OPEN → HALF_OPEN.
* **`gateway.py`:** `generate` takes a concurrency slot, calls the primary provider with
  retries (`_call_with_retries` → `_call_once`), and on failure tries the fallback.
* **Essential:** timeouts, bounded retries, and not retrying errors that cannot succeed.
  **Could drop:** in a small app, the breaker and the fallback.

### `app/services/rag/` — retrieval

* **`embeddings.py`:** `HashEmbedder` turns text into a vector by hashing words;
  `OpenAICompatibleEmbedder` calls a real model.
* **`knowledge_base.py`:** `chunk_text` splits a document; `ingest` embeds and stores chunks;
  `search` embeds the question and asks Qdrant for the nearest chunks.

### `app/monitoring/metrics.py`

* A list of Prometheus counters, gauges and histograms. Other modules import and increment them.

### `tests/`

* **`conftest.py`:** the `harness` fixture builds the real app with an in-memory Qdrant, a fake
  Redis and the mock provider, and creates three users (one per role).
* **`unit/`:** logic in isolation. **`api/`:** real HTTP requests against the app in memory.
  **`integration/`:** the same critical paths against real Redis and Qdrant containers.

---

## Part 2 — Learning notes

### JWT authentication

* **Purpose:** prove who is calling without the server remembering a session.
* **Why required:** with three replicas, any of them must be able to check a request alone.
* **How it works here:** login returns a token signed with a secret. Each request sends it in
  the `Authorization` header. The server checks the signature and expiry, then loads the user.
* **Code:** `app/core/security.py`, `app/api/deps.py`.
* **Flow:** `POST /auth/login` → `AuthService.login` → `create_access_token` → later
  `get_current_user` → `decode_access_token` → `UserRepository.get_by_id`.
* **Viva question:** "Why load the user if the token already has the role?"
* **Simple answer:** so that disabling an account, changing a role or changing a password takes
  effect at once, and a forged role in a token is useless.

### Password hashing

* **Purpose:** store passwords so that a database leak does not reveal them.
* **How it works here:** Argon2id with a random salt; verification runs in a worker thread.
* **Code:** `hash_password`, `verify_password` in `app/core/security.py`.
* **Viva question:** "Why not SHA-256?"
* **Simple answer:** SHA-256 is fast, so an attacker can try billions of guesses per second.
  Argon2 is deliberately slow and memory-hungry, which makes guessing expensive.

### Role-based access control

* **Purpose:** decide what an authenticated user may do.
* **How it works here:** each route lists its allowed roles through `require_role`. Anything not
  listed is denied.
* **Code:** `app/api/deps.py`; the tested matrix is in `tests/api/test_auth_api.py`.
* **Viva question:** "401 or 403?"
* **Simple answer:** 401 means "I do not know who you are". 403 means "I know who you are, and
  you may not do this".

### Rate limiting with Redis

* **Purpose:** stop one user from overusing the service or the LLM budget.
* **Why Redis:** a counter inside one replica is invisible to the others.
* **How it works here:** key `rl:chat:{user}:{window number}`; `INCR` and `EXPIRE` together.
* **Code:** `app/services/rate_limiter.py`.
* **Flow:** `ChatService.ask` → `ChatRateLimiter.check` → `RateLimiter.hit` → over the limit →
  `RateLimitedError` → HTTP 429 with `Retry-After`.
* **Viva question:** "What is the weakness of a fixed window?"
* **Simple answer:** a burst at the end of one window and the start of the next can reach twice
  the limit. A sliding window or token bucket fixes that.

### Response cache

* **Purpose:** avoid paying for the same answer twice.
* **How it works here:** the key is a hash of user id, question, model, temperature, prompt
  version and knowledge-base version. Entries expire after ten minutes.
* **Code:** `app/services/cache.py`.
* **Viva question:** "Why is the user id in the key?"
* **Simple answer:** otherwise one user could receive an answer generated for another.

### Retries, backoff and jitter

* **Purpose:** recover from temporary provider failures without making them worse.
* **How it works here:** up to two retries; the wait doubles each time and is multiplied by a
  random number; a provider's `Retry-After` is respected; nothing runs past the 40-second deadline.
* **Code:** `_call_with_retries`, `_allowed_retries`, `_retry_delay` in
  `app/services/llm/gateway.py`.
* **Viva question:** "Why not retry a 401 from the provider?"
* **Simple answer:** a wrong key stays wrong. Retrying only wastes time and adds load.

### Circuit breaker

* **Purpose:** stop calling a provider that is clearly down.
* **How it works here:** five failures in a row open the circuit; calls fail instantly for 30
  seconds; then one test call decides whether to close it again.
* **Code:** `app/services/llm/circuit_breaker.py`.
* **Viva question:** "How is it different from a retry?"
* **Simple answer:** a retry tries again; a breaker stops trying, so users get a fast error and
  the provider gets time to recover.

### Concurrency limit and load shedding

* **Purpose:** keep a replica alive under overload.
* **How it works here:** at most 20 LLM calls at once per replica; a request waits up to five
  seconds for a slot, then gets a 503.
* **Code:** `_acquire_slot` in `gateway.py`.
* **Viva question:** "Why reject instead of queueing?"
* **Simple answer:** an unlimited queue grows until everything is slow and memory runs out. A
  quick refusal lets the client retry later.

### RAG and embeddings

* **Purpose:** let the model answer from our own documents.
* **How it works here:** documents are split into chunks; each chunk becomes a vector; a
  question becomes a vector; Qdrant returns the closest chunks; they are added to the prompt.
* **Code:** `app/services/rag/`, `app/repositories/documents.py`.
* **Flow:** `POST /documents` → `KnowledgeBase.ingest` → `chunk_text` → `embed` →
  `DocumentRepository.add`. Then `POST /chat` → `KnowledgeBase.search` → `query_points`.
* **Viva question:** "Is your search semantic?"
* **Simple answer:** not by default. The built-in embedder matches shared words. A real embedding
  model can be configured, but I did not test one.

### Qdrant as the database

* **Purpose:** persistent storage for vectors and application records.
* **How it works here:** one vector collection and three collections without vectors.
* **Code:** `app/repositories/`, `app/database/bootstrap.py`.
* **Viva question:** "Why not PostgreSQL?"
* **Simple answer:** one database kept the project small, and my queries are only lookups,
  filters and vector search. I lose transactions and constraints, so for production I would use
  PostgreSQL for users and records; only the repository files would change.

### Health checks

* **Purpose:** let machines and people know whether the service works.
* **How it works here:** live = process up; ready = database reachable; health = full picture.
* **Code:** `app/api/routes/ops.py`.
* **Viva question:** "Why is Redis not part of readiness?"
* **Simple answer:** chat still works without Redis. If readiness failed, the load balancer would
  remove every replica and cause a full outage.

### Metrics and logs

* **Purpose:** see traffic, errors, latency and cost.
* **Code:** `app/monitoring/metrics.py`, middleware in `app/main.py`, `app/core/logging.py`.
* **Viva question:** "Why the route template and not the URL as a label?"
* **Simple answer:** every distinct label value creates a new time series. URLs with ids would
  create millions.

### Docker, Compose and nginx

* **Purpose:** the same environment everywhere, and real load balancing.
* **How it works here:** one image; Compose runs three copies; nginx sends requests to them in
  turn; an `init` job prepares the database first.
* **Code:** `Dockerfile`, `docker-compose.yml`, `docker/nginx.conf`.
* **Viva question:** "Is this highly available?"
* **Simple answer:** no. It is one machine. It shows the design; real availability needs several
  machines and managed data stores.

---

## Part 3 — Study before submission

In this order. For each item, be able to explain it with the file open and without notes.

1. `ChatService.ask` and its helpers — the whole request in five steps.
2. `LLMGateway`: `generate`, `_call_with_retries`, `_call_once`, `_allowed_retries`,
   `_retry_delay`. Draw the flow on paper once.
3. `CircuitBreaker`: the three states and what `release_trial` is for (a trial call that ended
   with an error unrelated to provider health must not leave the breaker stuck).
4. `get_current_user` and `require_role`.
5. `RateLimiter.hit` and the two failure policies (chat fails open, login fails closed).
6. `user_id_for` and why it replaces a unique constraint.
7. `build_cache_key` and the knowledge-base version.
8. `HashEmbedder.embed_one` and `chunk_text`.
9. The middleware in `app/main.py`.
10. `tests/conftest.py`: how the `harness` fixture replaces Redis, Qdrant and the LLM.
11. `docker-compose.yml` and `docker/nginx.conf`, line by line.

Then change something small yourself and make the tests pass again. Three suggestions: change
the chat rate limit and its test; add a field to `/health`; add a new scripted failure to the
mock provider and a test for it. Being able to modify the code is the best evidence that you
understand it.
