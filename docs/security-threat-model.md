# Security threat model

Scope: the API in this repository, run with Docker Compose. Likelihood and impact are
qualitative (Low / Medium / High). "Implemented" means there is code for it and, where noted, a
test. Everything under "Proposed" is future work.

## 1. Assets

| Asset | Why it matters |
|---|---|
| User credentials (password hashes) | Account takeover; password reuse on other sites |
| Access tokens and the JWT signing secret | Whoever holds the secret can mint any identity |
| LLM API key and quota | Direct financial loss |
| Chat content and knowledge-base documents | May contain personal or confidential information |
| Admin capability | Controls users, documents and metrics |
| Service availability | The product |

## 2. Trust boundaries

```
Internet ──▶ nginx ──▶ FastAPI replicas ──▶ Redis, Qdrant        (internal network only)
 untrusted             validates everything   trusted stores
                              │
                              └──▶ LLM provider (third party: receives question + context)
```

All client input is untrusted: bodies, headers, tokens, and the text of ingested documents.

## 3. Threats

### T1 — Credential exposure

| | |
|---|---|
| Attack | Database leak followed by offline cracking; weak or reused passwords; credentials committed to Git |
| Likelihood / impact | Medium / High |
| Implemented | Argon2id hashing with a per-password salt (`app/core/security.py`). Password policy on creation: ≥ 10 characters, a letter and a digit, must not contain the username. Hashes and passwords never appear in any response (tested) or log. No default password: the first admin comes from environment variables, and `scripts/make_env.py` generates a random one |
| Residual risk | No check against breached-password lists; no MFA; a user may still choose a guessable password that satisfies the policy |
| Proposed | Delegate login to an identity provider with MFA (OIDC); breached-password check |

### T2 — Token theft

| | |
|---|---|
| Attack | Token intercepted on the network, read from logs, or stolen from the client |
| Likelihood / impact | Medium / High |
| Implemented | 30-minute expiry. Signature, expiry and required claims verified with the algorithm pinned to HS256, so `alg=none` and algorithm-confusion tokens are rejected (tested). Tokens are never logged; a redaction filter masks bearer tokens and JWT-shaped strings. The user's active flag and role are re-read from the database on every request, so deactivating an account kills its tokens immediately (tested) |
| Residual risk | A stolen token works until it expires or the account is deactivated. **No TLS in the local stack** — traffic is plain HTTP on localhost. One shared HS256 secret: every service that can verify can also sign |
| Proposed | TLS terminated at the load balancer, HSTS; `jti` denylist in Redis for logout/revocation; short-lived access tokens with refresh tokens; asymmetric signing (RS256/ES256) via an identity provider |

### T3 — Brute-force and credential stuffing

| | |
|---|---|
| Attack | Automated password guessing against `/auth/login` |
| Likelihood / impact | High / Medium |
| Implemented | Redis throttle per username + client IP: 5 failures → locked for 300 s with `429` and `Retry-After` (tested). **Fails closed**: if Redis is down, login returns 503 instead of allowing unlimited guesses (tested). One generic error for unknown user, wrong password and disabled account; a dummy hash is verified for unknown users so timing does not reveal which usernames exist. The client IP is taken from `X-Real-IP` only when the app is behind our own nginx, which overwrites that header |
| Residual risk | A distributed attack from many IPs gets 5 guesses per IP per window per username; deliberate lockout of a known username from one IP (denial of service against that IP only). A lockout applies to username + IP, not globally per account |
| Proposed | Global per-account failure counter with exponential lockout; CAPTCHA or proof-of-work after repeated failures; WAF bot rules; MFA |

### T4 — Excessive usage and cost abuse

| | |
|---|---|
| Attack | A user or stolen account sends many or very large requests to run up the LLM bill or exhaust quota for others |
| Likelihood / impact | High / High |
| Implemented | Per-user rate limit in Redis shared by all replicas (tested with two limiter instances and, against real Redis, with 50 concurrent hits). Question limited to 4,000 characters; request body limited (nginx `client_max_body_size` and a `Content-Length` check); output capped by `LLM_MAX_OUTPUT_TOKENS`; model allow-list so a client cannot select an expensive model (tested); per-replica concurrency cap with load shedding; `READ_ONLY` role cannot call the LLM at all; token usage recorded per request for auditing |
| Residual risk | Fixed window allows up to 2× the limit across a boundary. While Redis is down the limiter falls back to a per-process cap (limit × replicas). There is no monetary or token *budget*, only a request count. The body-size check trusts `Content-Length`; a chunked upload is bounded only by nginx |
| Proposed | Per-user and global token budgets (TPM) in Redis; billing alerts; sliding-window or token-bucket limiter |

### T5 — Prompt injection (including poisoned documents)

| | |
|---|---|
| Attack | Text in the question, or in a document retrieved by RAG, instructs the model to ignore its rules, reveal the system prompt, or produce harmful output ("indirect" injection when it comes from a document) |
| Likelihood / impact | High / Medium (in this system) |
| Implemented | The system prompt is fixed in code (`app/services/llm/base.py`) and cannot be supplied by clients. User text and retrieved passages travel only in the user message, inside explicit `<context>` / `<question>` delimiters, and the system prompt states that both are untrusted data. **The model has no tools, no credentials and no access to other users' data**, so a successful injection can only change the text of that user's own answer. No secret is ever placed in a prompt. The answer is returned as JSON data, never executed or rendered as HTML by this service. Only ADMIN can add documents (tested) |
| Residual risk | **Prompt injection cannot be fully prevented**; a model can still be talked into ignoring instructions. Delimiters are a convention the model may not honour, and a document containing a literal `</context>` could confuse it. A malicious or careless admin can poison the shared knowledge base for all users. A client that renders the answer as HTML must escape it |
| Proposed | Escape delimiter look-alikes in retrieved text; provenance and review workflow for ingested documents; output filtering; injection test suite in CI; per-tenant knowledge bases |

### T6 — Sensitive information in logs

| | |
|---|---|
| Attack | Logs shipped to a third party or read by staff expose passwords, tokens or user questions |
| Likelihood / impact | Medium / Medium |
| Implemented | Logs contain request id, route template, status, latency and user id — not usernames on the request line, not questions, answers, passwords, tokens or API keys. Validation errors name the failing field but never echo the submitted value (tested with a password). A redaction filter masks bearer tokens, JWTs, `sk-…` keys and `password=`-style pairs as a safety net (tested). The nginx access log records method, path, status and timings only. Error responses never include stack traces or provider messages (tested) |
| Residual risk | The redaction filter is pattern-based and will miss unknown formats. Chat text is stored in Qdrant when `STORE_CHAT_CONTENT=true` (the default) and is not encrypted at the application level. Questions are sent to the LLM provider |
| Proposed | Retention job; encryption at rest on the data volumes; PII detection before storage; a data-processing agreement with the provider |

### T7 — Secret leakage through Git

| | |
|---|---|
| Attack | An API key or `.env` file is committed and pushed |
| Likelihood / impact | Medium / High |
| Implemented | `.env` is git-ignored and excluded from the Docker build context; only `.env.example` without values is committed. All secrets come from environment variables. In `prod` the app refuses to start with a default or short `JWT_SECRET` (tested). The Kubernetes Secret manifest is a template with placeholders |
| Residual risk | Nothing technically stops someone from pasting a key into a tracked file. No secret scanner has been run on this repository |
| Proposed | `gitleaks` as a pre-commit hook and in CI; GitHub secret scanning and push protection. **If a secret leaks: rotate it immediately** — removing it from history afterwards is secondary |

### T8 — Dependency vulnerabilities

| | |
|---|---|
| Attack | A known vulnerability in a library or base image is exploited |
| Likelihood / impact | Medium / High |
| Implemented | All dependencies pinned to exact versions. `pip-audit -r requirements.txt` on 2026-10-03: "No known vulnerabilities found" ([evidence](evidence/pip-audit.txt)). Slim base image, multi-stage build with no build tools in the runtime image, non-root user (uid 10001, verified with `docker compose exec app id`) |
| Residual risk | Transitive dependencies are not hash-locked. The audit is a point-in-time result. The container image itself was not scanned |
| Proposed | Dependabot or Renovate; `pip-audit` on every CI run (present in the workflow, not yet executed on GitHub); image scanning (Trivy or ECR scanning); hash-locked requirements |

### T9 — Unauthorised administrative access

| | |
|---|---|
| Attack | A normal user reaches admin functions through a missing check, a forged role claim, or an exposed endpoint |
| Likelihood / impact | Low / High |
| Implemented | Deny by default: every protected route declares its roles through `require_role`. The role used for the decision is read from the database, **not** from the token: a correctly signed token carrying `role=ADMIN` for a USER account still gets 403 (tested). The full role matrix is tested for all three roles. Request bodies reject unknown fields, so a client cannot send `role` or `user_id` where they are not expected. There is no public sign-up; only an admin creates users. An admin cannot deactivate or demote themself. Admin actions write an audit event (who, what, when; never the password). `/metrics` needs an ADMIN token or a dedicated scrape token compared in constant time |
| Residual risk | A single compromised admin account has full control; audit events are stored in the same database an admin could tamper with through direct access; Qdrant and Redis have no passwords in the Compose stack and rely on network isolation |
| Proposed | MFA for admins; append-only audit log shipped elsewhere; authentication and TLS on Redis and Qdrant; separate admin network path |

## 4. Other hardening in place

* Security headers on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
* CORS is off unless origins are listed explicitly, and never allows credentials.
* A client-supplied `X-Request-ID` is accepted only if it matches a safe pattern (prevents log
  injection); otherwise a new one is generated.
* Qdrant and Redis publish no host ports in the default Compose file.
* Kubernetes manifests [CONFIGURED]: `runAsNonRoot`, read-only root filesystem, all capabilities dropped.

## 5. Review status

| Check | Result |
|---|---|
| Automated security-relevant tests (auth, RBAC, throttling, error leakage, redaction) | Passing, part of the 146-test suite |
| Ruff with the `S` (flake8-bandit) rule set | Clean |
| `pip-audit` | No known vulnerabilities (2026-10-03) |
| Secret scan of the repository history | **Not run** |
| Container image scan | **Not run** |
| Penetration test or external review | **Not done** |
