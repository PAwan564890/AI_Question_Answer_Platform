# Demo Script (5 minutes)

A timed script for a five-minute recorded or live demonstration. Only implemented features are shown. Everything runs locally with the mock LLM; no real provider, no cloud.

- "On screen:" is what to do. Commands are for Windows PowerShell and use `curl.exe` (not the `curl` alias).
- "Say:" is the spoken line. The spoken lines total about 730 words, which is five minutes at a calm pace.
- JSON bodies are read from small files (`-d "@file.json"`), because quoting JSON inline differs between PowerShell versions.

See also: [technical report](technical-report.md), [viva preparation](viva-prep.md).

---

## Before recording (off camera)

Run these once in the repository root, in the PowerShell window that will be recorded. They start the stack, create two demo accounts with a random password that is never displayed, and prepare the request bodies.

```powershell
# 1. Stack up and verified
docker compose up --build -d
python scripts/smoke_test.py            # expect: RESULT: ALL CHECKS PASSED

# 2. Helpers and tokens (nothing secret is printed)
$base    = "http://localhost:8000"
$adminPw = ((Get-Content .env | Where-Object { $_ -like 'ADMIN_PASSWORD=*' }) -split '=', 2)[1]
function Get-Token($u, $p) {
    (Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType 'application/json' `
        -Body (@{ username = $u; password = $p } | ConvertTo-Json)).access_token
}
$admin  = Get-Token 'admin' $adminPw
$demoPw = (-join ((48..57) + (97..122) | Get-Random -Count 14 | ForEach-Object { [char]$_ })) + 'a1'

# 3. Demo accounts: one USER, one READ_ONLY
foreach ($pair in @(@('demo_user', 'USER'), @('demo_reader', 'READ_ONLY'))) {
    Invoke-RestMethod -Method Post -Uri "$base/admin/users" -ContentType 'application/json' `
        -Headers @{ Authorization = "Bearer $admin" } `
        -Body (@{ username = $pair[0]; password = $demoPw; role = $pair[1] } | ConvertTo-Json) | Out-Null
}
$reader = Get-Token 'demo_reader' $demoPw

# 4. Request bodies (ASCII so that no byte-order mark breaks the JSON)
#    Stay in the repository folder: the docker compose commands below need it.
$d = "$env:TEMP\demo"
New-Item -ItemType Directory -Force $d | Out-Null
'{"question": "What is a circuit breaker?"}'              | Set-Content -Encoding ascii "$d\hi.json"
'{"question": "Which port does the zephyr protocol use?"}' | Set-Content -Encoding ascii "$d\q.json"
'{"title": "Zephyr protocol note", "text": "The zephyr protocol uses port 4242 for telemetry uploads.", "source": "demo"}' |
    Set-Content -Encoding ascii "$d\doc.json"
Clear-Host
```

Notes:

- If `demo_user` already exists from a rehearsal, account creation returns 409 and the old password applies. Use fresh names (for example `demo_user2`) or reset the data with `docker compose down -v` and start again.
- Wait at least 60 seconds after the last rehearsal so the rate-limit window of the demo user is empty.
- Open two browser tabs: the architecture diagram (`docs/architecture.md`, section 3, rendered on GitHub) and `http://localhost:8000/docs`.

---

## 0:00–0:30 Problem and objective

**On screen:** Title slide or the first page of `docs/technical-report.md`.

**Say:**

> Calling a language model once is easy. Offering it to many users as a service is not, because the model is slow, it costs money per token, and it fails in several different ways. My project is a question-answering API built like a small production service. It authenticates users, restricts them by role, limits how fast they can call, grounds answers in our own documents, and keeps working when a dependency fails. I will show what runs today and say clearly what is only designed.

## 0:30–1:15 Architecture, stack, implemented versus proposed

**On screen:** The Mermaid diagram of the Compose topology (`docs/architecture.md`, section 3). Point at each box as it is named.

**Say:**

> This is what actually runs. A client talks to nginx, which load-balances across three identical FastAPI replicas. The replicas keep no state of their own. Redis holds what they must share: rate limits, the login throttle, and the response cache. The only database is Qdrant, a vector database, chosen deliberately instead of PostgreSQL. It stores the document vectors for retrieval-augmented generation, and also users, chat records and audit events as plain payloads. The cost is no transactions and no unique constraints. The language model sits behind a gateway with timeouts, retries, a circuit breaker and load shedding. By default it is a mock, so no real provider was ever called. The Kubernetes files are configured but never run, and everything about AWS is proposed only.

## 1:15–2:15 Running stack, Swagger UI, health

**On screen:**

```powershell
docker compose ps
```

Then the browser tab `http://localhost:8000/docs`; scroll once through the endpoint groups (auth, chat, knowledge base, admin, ops). Expand `GET /health`, click "Try it out", then "Execute". Back in the terminal:

```powershell
curl.exe -s $base/health
curl.exe -s -i $base/health/ready
```

**Say:**

> The stack is already running. Docker Compose shows nginx, three application containers, Qdrant and Redis. The init job has finished: it created the collections and seeded the first admin from environment variables. Only nginx publishes a port. This is the Swagger page that FastAPI generates from the same models that validate requests. I call the health endpoint. The database and Redis are fine, the model is the mock, and the embedder is the offline hash embedder. There are three health endpoints for three questions. Liveness asks whether the process is running. Readiness asks whether it should receive traffic, and it fails when the database is unreachable. Health is the summary for a person. When I stopped Redis in testing, health reported degraded, but chat kept working and the replicas stayed in rotation.

## 2:15–3:00 Login, chat, 403 and 401

**On screen:**

```powershell
$user = Get-Token 'demo_user' $demoPw
curl.exe -s -H "Authorization: Bearer $user" $base/auth/me

curl.exe -s -H "Authorization: Bearer $user" -H "Content-Type: application/json" -d "@$d\hi.json" $base/chat

curl.exe -s -i -H "Authorization: Bearer $reader" -H "Content-Type: application/json" -d "@$d\hi.json" $base/chat

curl.exe -s -i -H "Content-Type: application/json" -d "@$d\hi.json" $base/chat
```

Point at: `"role":"USER"`; the `[mock]` answer with `usage` and `latency_ms`; `HTTP/1.1 403` with code `FORBIDDEN`; `HTTP/1.1 401` with code `UNAUTHENTICATED`.

**Say:**

> I log in as a normal user. Passwords are stored as Argon2 hashes, and the login returns a signed token that lasts thirty minutes. The me endpoint confirms the role is USER. Now I ask a question. The answer comes from the mock, marked clearly, with token usage, latency and the retry count. The same request with a read-only account returns 403, forbidden. With no token at all it returns 401. Every error has the same shape, with a code and a request ID that also appears in the logs.

## 3:00–3:45 RAG, cache, rate limit, history, metrics

**On screen:**

```powershell
# ingest as ADMIN
curl.exe -s -H "Authorization: Bearer $admin" -H "Content-Type: application/json" -d "@$d\doc.json" $base/documents

# grounded answer with sources, then the same question again (cache)
curl.exe -s -H "Authorization: Bearer $user" -H "Content-Type: application/json" -d "@$d\q.json" $base/chat
curl.exe -s -H "Authorization: Bearer $user" -H "Content-Type: application/json" -d "@$d\q.json" $base/chat

# rate limit: keep asking until the shared limiter answers 429
1..21 | ForEach-Object { curl.exe -s -o NUL -w "%{http_code} " -H "Authorization: Bearer $user" -H "Content-Type: application/json" -d "@$d\q.json" $base/chat }

# history (stored in Qdrant) and metrics (ADMIN only)
curl.exe -s -H "Authorization: Bearer $user" "$base/chat/history?limit=2"
curl.exe -s -H "Authorization: Bearer $admin" $base/metrics | Select-String "^cache_requests_total|^rate_limit_events_total|^llm_requests_total"
```

Point at: `chunk_count` in the ingest response; `4242` and the `sources` list in the first answer; `"cached":true` in the second; the run of `200` followed by `429` (the limit is 20 per minute and three calls were already made, so the 18th call in the loop is the first 429); `"cached":true` in a history item; the three counters.

If a counter shows zero, run the metrics command again: nginx sends each scrape to one replica, and counters are per replica.

**Say:**

> As admin I ingest a short document. It is split into chunks, embedded, and stored in Qdrant. Now the user asks about it. The answer contains the fact from the document and lists its sources. I ask again, and cached is true: it came from Redis, with no model call. I keep asking, and after twenty requests in a minute the limiter returns 429, even though the requests went to different replicas. The history endpoint shows the records, stored in Qdrant. The metrics endpoint, for admins only, shows the cache, rate-limit and model counters.

## 3:45–4:30 Docker, replicas, scaling, load-test honesty

**On screen:**

```powershell
1..6 | ForEach-Object { curl.exe -s -i $base/health/live | Select-String "x-served-by" }
docker compose exec app id -u
```

Point at the three different `X-Served-By` values and at `10001`. Then show the proposed AWS diagram (`docs/scaling-analysis.md`, section 13) and the load-test table (same file, section 12).

**Say:**

> Each response names the replica that served it. Six calls show three different containers, and they run as a non-root user. Because the replicas are stateless, the path from one EC2 instance is to move Redis and Qdrant out, put a load balancer in front, and run the same image on ECS. That part is proposed, not built. What I measured is on my laptop with the mock model. With one second of simulated latency, three replicas gave about fifty-three requests per second, which matches the prediction of sixty slots. With zero latency I saw about one hundred and eighteen, but that is a lower bound because my load generator was the bottleneck. I did not test five hundred requests per second, and I never called a real model.

## 4:30–5:00 Decisions, limitations, future work

**On screen:** The limitations list (`README.md`, section 16), then future improvements (section 17).

**Say:**

> Three decisions shaped this project. One datastore, a vector database, with its trade-offs written down. All shared state in Redis, with a clear choice between failing open and failing closed. And a gateway that treats the model as slow and unreliable. The main limitations: the default embedder matches words, not meaning; tokens cannot be revoked early; and the datastores are single nodes. Next I would test a real provider, add real embeddings, and run the Kubernetes files. Thank you.

---

## After the demo (optional clean-up)

```powershell
# remove the demo document so the knowledge base is empty again
$docs = Invoke-RestMethod -Uri "$base/documents" -Headers @{ Authorization = "Bearer $admin" }
$docs | Where-Object { $_.title -eq 'Zephyr protocol note' } | ForEach-Object {
    Invoke-RestMethod -Method Delete -Uri "$base/documents/$($_.doc_id)" -Headers @{ Authorization = "Bearer $admin" }
}
```

---

## Recording checklist

Preparation

- [ ] Docker Desktop is running; `docker compose ps` shows nginx, three `app` containers, Qdrant and Redis.
- [ ] `python scripts/smoke_test.py` ends with `RESULT: ALL CHECKS PASSED`.
- [ ] The "Before recording" block was run in the window being recorded: `$base`, `$admin`, `$reader`, `$demoPw` and `Get-Token` exist; `demo_user` and `demo_reader` exist.
- [ ] The three JSON files exist in `$d` (`hi.json`, `q.json`, `doc.json`) and the terminal is still in the repository folder.
- [ ] At least 60 seconds have passed since the last `/chat` call by `demo_user`.
- [ ] No "Zephyr protocol note" document is left from a rehearsal (otherwise two sources appear).

Privacy

- [ ] `.env` is closed in every editor and is never opened or printed on screen.
- [ ] The admin password is never typed or displayed; `$adminPw` is read from `.env` off camera.
- [ ] Token values are never printed (`$user`, `$admin`, `$reader` are used only inside commands); the JWT secret is never shown.
- [ ] The terminal was cleared (`Clear-Host`) after setup; the scroll-back contains nothing secret.
- [ ] Browser: no bookmarks bar, no unrelated tabs, notifications off.

Presentation

- [ ] Terminal font enlarged (at least 16 pt) and window wide enough that JSON does not wrap badly.
- [ ] Commands are ready in the PowerShell history (arrow-up) or in a notes window to paste; nothing is typed from memory.
- [ ] A backup recording exists of the slow or risky steps (`docker compose ps`, the rate-limit loop, the metrics command) in case they misbehave live.
- [ ] The architecture diagram, the AWS diagram and the load-test table are open in tabs in the order they are needed.
- [ ] Rehearsed twice from start to finish with a timer; total between 4:45 and 5:00.

Honesty

- [ ] Only implemented features are demonstrated. Kubernetes is described as configured and not run; AWS as proposed.
- [ ] The load figures are stated with their conditions: laptop, mock LLM, load generator as bottleneck; 500 RPS not tested; no real provider called.
