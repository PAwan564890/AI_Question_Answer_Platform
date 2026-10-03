# Migration plan: from one EC2 server to a production architecture

**Everything in this document is [PROPOSED].** None of it has been executed. It answers the
assessment's scenario: a Python LLM application runs on a single EC2 server, works for about 10
users, sometimes becomes slow or crashes, and must now serve about 10,000 users.

## 1. Why the current setup fails

| Symptom | Likely cause on a single server | Fix (phase) |
|---|---|---|
| Slow for everyone when the LLM is slow | Requests wait without timeouts; a blocking server runs out of workers | Async I/O, timeouts, deadline, concurrency cap (already in this code base; rolled out in phase 1) |
| Crashes under load | No limit on in-flight work; memory grows until the process dies | Load shedding, rate limits, more than one instance (1–2) |
| One crash is a full outage | Single process on a single machine | Two or more instances behind a load balancer (1), multi-AZ (2) |
| Data at risk | Database on the same disk as the app | Managed, replicated data stores with backups (1) |
| Risky deployments | SSH and restart | Images, CI/CD, rolling or blue/green (2) |
| Nobody knows it is failing until users complain | No metrics or alerts | Health checks, metrics, alarms (1, 3) |
| Secrets in a file on the server | Manual configuration | Secrets Manager / SSM Parameter Store (1) |

## 2. Principles

1. **One change at a time**, each reversible, each with a measurable success criterion.
2. **Move state out first.** Once data and secrets are off the server, the server is disposable.
3. **Run old and new in parallel** and shift traffic gradually; never a "big bang" cut-over.
4. **Capacity follows evidence**: sizes below are starting points to be corrected by metrics.

## 3. Phases

### Phase 0 — Baseline (today)

* **State**: one EC2 instance, application and data together, about 10 users.
* **Do now, at no risk**: add `/health`, metrics and structured logs; record a week of baseline
  numbers (requests/minute, LLM latency, error rate, tokens/day); take a snapshot/backup and
  *test restoring it*; write down every secret and config value the server holds.
* **Exit criterion**: we can say what "normal" looks like and can restore the data.

### Phase 1 — Containerise, externalise state, add a second instance

* **Goal**: remove the single point of failure without changing the architecture's shape.
* **Steps**
  1. Build the Docker image in CI; run the *same image* on the existing server first.
  2. Move secrets to AWS Secrets Manager (or SSM Parameter Store); the container receives them
     as environment variables at start. Rotate every secret that ever lived in a file.
  3. Create managed data stores: ElastiCache for Redis; a managed or self-hosted replicated
     Qdrant (or Qdrant Cloud). Copy data with a snapshot, then keep it in sync (dual-write or a
     short write freeze, section 4).
  4. Put an Application Load Balancer in front of **two** instances in different availability
     zones, health-checked on `/health/ready`, TLS terminated at the ALB.
  5. Lower the DNS TTL to 60 s a day ahead, then point the DNS record at the ALB.
* **Risks**: data divergence during the copy; a secret missed in the inventory; latency between
  the app and the new data stores.
* **Rollback**: DNS back to the old server (still running, untouched) — minutes, because the TTL
  was lowered. The old data store stays authoritative until phase 1 is declared done.
* **Cost sensitivity**: roughly doubles compute and adds a load balancer and managed stores.
  Still small; this phase buys reliability, not capacity.

### Phase 2 — Orchestration, autoscaling, safe deployments

* **Goal**: capacity that follows traffic, and deployments that cannot take the service down.
* **Steps**
  1. Move the containers to **ECS on Fargate** (smallest operational burden) or **EKS** (if the
     team already runs Kubernetes; manifests in `k8s/` are a starting point).
  2. Autoscale on in-flight requests per task or ALB `RequestCountPerTarget`, not CPU alone;
     minimum 3 tasks across zones. Scale out fast, scale in slowly.
  3. CI/CD pipeline: lint → tests → image scan → push → **rolling or blue/green deployment** with
     automatic rollback when health checks fail. Graceful shutdown (already implemented) plus ALB
     connection draining means in-flight requests finish.
  4. Run the schema bootstrap (`python -m app.database.seed`) as a one-off task per release.
  5. Infrastructure as code (Terraform or CloudFormation) so the environment can be rebuilt.
* **Risks**: misconfigured health checks causing restart loops; scaling out the API beyond what
  the LLM quota allows (more replicas, same quota → more 429s).
* **Rollback**: redeploy the previous image tag (one command); keep the phase 1 instances for a
  week as a warm fallback behind the same ALB.
* **Cost sensitivity**: compute now varies with traffic. The LLM bill is already the larger item.

### Phase 3 — Protect the provider and the budget

* **Goal**: survive spikes to 500 RPS and provider incidents without crashing or overspending.
* **Steps**
  1. **Queue + workers** (SQS) for long generations and bulk ingestion; workers consume at the
     provider's allowed rate. Interactive requests stay synchronous.
  2. **Global provider budget** in Redis: shared RPM/TPM counters so the fleet as a whole stays
     under quota; requests over budget are queued or rejected early with `Retry-After`.
  3. **Second provider or second key** behind the existing fallback chain; per-provider circuit
     breakers; shared breaker state in Redis.
  4. **Per-user and per-tenant token quotas**; model tiering (a cheaper model for simple
     questions); wider caching where privacy allows.
  5. **Dashboards and alerts**: error rate, p95 latency, circuit state, fallback rate, queue age,
     token spend per hour. An on-call runbook for "provider down" and "quota exhausted".
  6. **WAF** rules and edge rate limiting at the load balancer.
* **Risks**: queue semantics (duplicate processing → idempotency keys required); answer quality
  differences between providers; alert fatigue.
* **Rollback**: each item is behind a configuration flag; turning it off restores phase 2 behaviour.
* **Cost sensitivity**: this phase *reduces* the dominant cost (tokens) and caps the worst case.

### Phase 4 — Enterprise identity and beyond

* **Goal**: replace local passwords with single sign-on; prepare for organisational growth.
* **Steps**: an identity provider (Cognito, Entra ID, Keycloak, Auth0) with OAuth2/OIDC;
  the service validates RS256 tokens through the IdP's JWKS endpoint and maps groups to roles
  (see [architecture.md](architecture.md#6-evolution-to-ssooidc-proposed)); an API gateway in
  front for coarse authentication, quotas and API keys for machine clients; run both login
  methods in parallel during the transition, then disable `/auth/login`.
* **Multi-region** only if a requirement justifies it (data-residency law, or an availability
  target one region cannot meet). It multiplies cost and complexity, and the LLM provider is
  usually the less available component anyway.
* **Rollback**: keep local login enabled until SSO has been stable for an agreed period.

## 4. Migrating with minimal downtime

1. **Prepare in parallel.** The new environment is built and tested next to the old one with
   production-like data. The old server is not modified.
2. **Data.** Take a snapshot and restore it into the new store. For the remaining gap either
   (a) dual-write from the application for a short period and compare, or (b) accept a brief
   read-only window (minutes) at a quiet hour while the final delta is copied. For a 10-user
   system option (b) is the honest, simple choice; dual-writing is worth its complexity only
   when a write freeze is unacceptable.
3. **Shift traffic gradually.** Weighted DNS (Route 53) or ALB weighted target groups: 5 % →
   25 % → 50 % → 100 %, watching error rate and latency at each step for an agreed soak time.
4. **Define rollback before starting**: the trigger (for example error rate above an agreed
   threshold for 5 minutes), the action (weights back to the old target), and who decides.
5. **Keep the old server** until the new one has carried full traffic through at least one
   normal peak. Then decommission it and rotate any secret it held.

Stateless tokens help here: a JWT issued by the old environment is valid in the new one as long as
both share the signing key, so users are not logged out during the shift.

## 5. Secrets and configuration

| Kind | Where | Notes |
|---|---|---|
| Secrets (JWT signing key, LLM API keys, admin bootstrap password, data-store credentials) | Secrets Manager / SSM SecureString, injected as environment variables at task start | Access by IAM role per service; rotation schedule; never in images, repositories, logs or task definitions in plain text |
| Non-secret configuration (limits, timeouts, feature flags, URLs) | Environment variables from the task definition / ConfigMap | Versioned with the infrastructure code; one place in the app reads them (`app/core/config.py`) |
| Per-environment differences | Separate parameter paths (`/prod/...`, `/staging/...`) | The same image runs everywhere; only configuration differs |

The application already refuses to start in `prod` with a weak or default `JWT_SECRET`, which
turns a dangerous misconfiguration into an immediate, visible deployment failure.

## 6. Capacity sketch for 10,000 users

Registered users are not concurrent requests. If 10 % are active at a peak hour and each sends a
question every 30 seconds, that is about 33 RPS; the assessment's 100 RPS is a comfortable
design point and 500 RPS a spike. These participation figures are assumptions for illustration
and should be replaced with measured ones in phase 0. The gateway arithmetic for those rates is in
[scaling-analysis.md](scaling-analysis.md#2-arithmetic); the binding constraint is the provider's
quota, to be confirmed with the provider before phase 3.
