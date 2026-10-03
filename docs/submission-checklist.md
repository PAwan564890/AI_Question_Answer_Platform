# Submission package and checklist

## 1. What is in the package

| # | Deliverable | Location |
|---|---|---|
| 1 | Source code, tests, Docker and Compose files | repository root, `app/`, `tests/`, `docker/` |
| 2 | README (setup, API, configuration, limitations) | [`README.md`](../README.md) |
| 3 | Technical report (about 10,000 words; 30–35 pages exported) | [`technical-report.md`](technical-report.md) |
| 4 | Architecture and diagrams | [`architecture.md`](architecture.md); README §2; [`scaling-analysis.md`](scaling-analysis.md) §13 |
| 5 | Scaling analysis and migration plan | [`scaling-analysis.md`](scaling-analysis.md), [`migration-plan.md`](migration-plan.md) |
| 6 | Security threat model | [`security-threat-model.md`](security-threat-model.md) |
| 7 | Test report and raw evidence | [`test-report.md`](test-report.md), [`evidence/`](evidence/) |
| 8 | Final audit and compliance matrix | [`audit-report.md`](audit-report.md) |
| 9 | Five-minute demonstration script | [`demo-script.md`](demo-script.md) |
| 10 | Viva preparation | [`viva-prep.md`](viva-prep.md) |
| 11 | Code guide: module walk-through and learning notes | [`code-guide.md`](code-guide.md) |

## 2. Repository structure

```
ai-qa-platform/
├── app/
│   ├── main.py                  app factory and middleware
│   ├── container.py             wires long-lived objects
│   ├── api/deps.py              current user, require_role
│   ├── api/routes/              auth, chat, documents, admin, ops
│   ├── core/                    config, security, logging, errors
│   ├── models/  schemas/        domain objects; request and response models
│   ├── repositories/            Qdrant access
│   ├── services/                auth, chat orchestration, rate limiter, cache
│   ├── services/llm/            contract, mock, OpenAI-compatible adapter, breaker, gateway
│   ├── services/rag/            embeddings, knowledge base
│   ├── database/                client, bootstrap, seed (init job)
│   └── monitoring/metrics.py
├── tests/  unit/  api/  integration/
├── docker/nginx.conf
├── k8s/                         manifests (never run)
├── scripts/                     make_env, smoke_test, load_test, verify_llm
├── docs/                        the documents listed above, evidence/
├── .github/workflows/ci.yml
├── Dockerfile  docker-compose.yml  docker-compose.dev.yml
├── pyproject.toml  requirements.txt  requirements-dev.txt
├── .env.example  .gitignore  .gitattributes  .dockerignore
└── README.md
```

## 3. Pushing to GitHub

The repository exists locally with its history; nothing has been pushed.

1. **Check that no secret is staged or tracked.**

   ```bash
   git status
   ```

   ```bash
   git ls-files | grep -E "^\.env$" || echo ".env is not tracked"
   ```

2. **Create an empty repository on GitHub** (no README, no licence, no `.gitignore`: the local
   repository already has them). Choose public, or private with access for the assessors.

3. **Connect and push** (replace the URL with yours).

   ```bash
   git remote add origin https://github.com/<your-username>/ai-qa-platform.git
   ```

   ```bash
   git push -u origin main
   ```

4. **Check the result in a private browser window**: the README renders, the Mermaid diagrams
   draw, `.env` is absent, and the *Actions* tab shows the CI workflow. This will be its first
   run; if a step fails, read the log and fix it before submitting.

5. **Commit authorship.** The commits carry a `Co-Authored-By: Claude` trailer. If your
   assessment requires disclosing or avoiding AI assistance, decide how to handle that before
   pushing. Be prepared to explain every part of the code either way.

6. **If a secret is ever pushed by mistake: rotate it first** (new JWT secret, new API key), then
   remove it from history. Deleting the file in a later commit does not remove it.

## 4. Converting the report

The report is Markdown with Mermaid diagrams. Two reliable routes to a PDF or DOCX:

* Open `docs/technical-report.md` on GitHub (diagrams render), and print the page to PDF.
* In VS Code, install a Markdown-to-PDF extension that supports Mermaid, and export.

Check the page count after export. The text is about 10,000 words with four diagrams and many
tables, which should give roughly 30–35 pages at 11 pt with normal margins. The count was not measured,
because no converter was available during preparation.

## 5. Final checklist

Verified during the final audit (3 October 2026):

- [x] Fresh clone → `python scripts/make_env.py` → `docker compose up --build -d` works
- [x] Admin seeding works; no default password exists in the repository
- [x] `/auth/login`, `/chat`, `/health`, `/metrics` verified on the live stack
- [x] RBAC verified for all three roles (12 endpoints × 3 roles)
- [x] Rate limiting verified across replicas (smoke test) and on real Redis (integration test)
- [x] Provider timeout, failure, fallback and circuit breaker verified by tests (mock provider)
- [x] `pytest`: 150 passed; coverage 96 %; output recorded
- [x] `ruff`, `mypy`, `pip-audit` clean; output recorded
- [x] README commands executed from a fresh clone
- [x] Honesty labels present; no claim of cloud deployment, real-LLM testing or 500 req/s
- [x] Scaling analysis, migration plan, threat model and report consistent with the code
- [x] No secret in the working tree or history (pattern scan and exact-value search)
- [x] Demonstration script: every command rehearsed in PowerShell

To be done by the student:

- [ ] Read the README, the report and the viva notes until every component can be explained without notes
- [ ] (Recommended) Verify one real LLM request: [audit-report.md §4.2](audit-report.md)
- [ ] Create the GitHub repository, push, and confirm the Actions workflow passes
- [ ] Export the report and check the page count
- [ ] Add the two references marked "to be added by student" in the report
- [ ] Record the video (maximum 5 minutes) following `demo-script.md`; no secrets on screen
- [ ] Check the repository link and the video link in a private browser window
- [ ] Submit both links through the assessment form

## 6. Three things to say before being asked

1. No real LLM was called; the provider adapter is tested against stubbed responses only.
2. Nothing runs in a cloud; all measurements are from one laptop with a mock model, and 500
   requests/second was not tested.
3. The only database is a vector database. This is permitted by the assessment's wording, is not
   what a production system should use for user and audit data, and can be changed by replacing
   the repository layer.
