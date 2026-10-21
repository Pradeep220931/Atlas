# ATLAS

ATLAS is an engineering knowledge continuity application. Its intended purpose is to make system context, knowledge gaps, and handovers easier to inspect and validate. This repository currently contains a working demo/MVP foundation, not a production-complete continuity platform. This README distinguishes implemented behavior from demo-only screens and unfinished integrations.

## Contents

- [Current capabilities](#current-capabilities)
- [Technology stack](#technology-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Run locally on Windows](#run-locally-on-windows)
- [Demo accounts](#demo-accounts)
- [Configuration](#configuration)
- [Database and migrations](#database-and-migrations)
- [Backend API](#backend-api)
- [Frontend routes and roles](#frontend-routes-and-roles)
- [Integrations](#integrations)
- [Tests and builds](#tests-and-builds)
- [Known limitations](#known-limitations)
- [Security notes](#security-notes)

## Current capabilities

### Authentication and roles

- Login checks a user in the database and verifies the Argon2 password hash.
- Successful login returns a JWT signed using HS256.
- Protected API endpoints validate the bearer token, confirm that the user is active, and apply role checks where configured.
- The product has four roles: `manager`, `holder`, `incoming`, and `admin`.
- The frontend clears the saved token on logout and redirects protected pages to login when there is no authenticated user.

### Knowledge gaps and capture

- Authenticated users can list and inspect organization-scoped knowledge gaps.
- Managers and knowledge holders can submit an answer. The answer is persisted as a proposed `KnowledgeRecord`; submission alone does not validate the gap.
- Knowledge records can be listed for a gap, including proposal status and submitter/validator names.
- Managers can approve, reject, or request clarification on a proposed record. Approval marks the record and the gap as validated.
- Submission and review actions create audit-log entries.
- Gap and review lookups are scoped to the authenticated user's organization.

### Demo workspace

The seed script creates a FinPay / Engineering organization, five teams, five services, four demo users, knowledge areas, and three sample knowledge gaps. The front end includes overview, knowledge map, risk-area, knowledge, transition, integration, and administration views. Many values on those screens are illustrative demo content and should not be interpreted as live measurements; see [Known limitations](#known-limitations).

## Technology stack

| Area | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite, React Router, Lucide React |
| Backend | Python, FastAPI, Pydantic, Uvicorn, HTTPX |
| Persistence / ORM | SQLAlchemy 2 |
| Migrations | Alembic |
| Database | PostgreSQL with Psycopg; SQLite can be used for local demo development |
| Authentication | JWT / HS256 and Argon2 password hashing |
| External APIs | GitHub REST API and Jira REST API |
| Optional AI | Anthropic Claude via the official Python SDK (backend only) |

The frontend manifest currently uses `latest` for React, Vite, TypeScript, React Router, Lucide React, and the Vite React plugin. Python was exercised with version 3.12 in development. See `frontend/package.json` and `backend/requirements.txt` for dependency declarations.

## Architecture

```mermaid
flowchart LR
  Browser[React + TypeScript + Vite] -->|JSON API / bearer JWT| API[FastAPI]
  API --> ORM[SQLAlchemy]
  ORM --> DB[(PostgreSQL or local SQLite)]
  API --> GH[GitHub REST API]
  API --> Jira[Jira REST API]
  Alembic[Alembic migrations] --> DB
```

The frontend API wrapper is in `frontend/src/api.ts`; shared frontend session and page state live in `frontend/src/store.tsx`. FastAPI endpoints are currently collected in `backend/app/main.py`. SQLAlchemy entities live in `backend/app/models/entities.py`.

## Prerequisites

- Python 3.12 or a compatible Python version supported by the listed backend dependencies.
- Node.js and npm.
- GitHub/Jira credentials only if you intend to try their current summary-sync endpoints.
- For PostgreSQL operation, a reachable PostgreSQL database. Local demo development can use SQLite instead.

## Run locally on Windows

Commands below are for PowerShell from the repository root. The repository may already have a virtual environment at `venv`; create one if it does not exist.

### 1. Install backend dependencies

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

If the virtual environment already exists, activate that environment and install the requirements instead of recreating it.

### 2. Initialize and seed a local SQLite database

The backend loads `backend/.env` if present. `SUPABASE_DATABASE_URL` takes precedence over `DATABASE_URL`, so explicitly set both variables in the current PowerShell session when choosing SQLite.

```powershell
Set-Location backend
$env:SUPABASE_DATABASE_URL = 'sqlite:///./atlas-runtime.db'
$env:DATABASE_URL = 'sqlite:///./atlas-runtime.db'
..\venv\Scripts\python.exe -m alembic upgrade head
..\venv\Scripts\python.exe -m app.seed
```

The seed is designed to add the sample FinPay data without re-creating existing seed rows. Keep this database for local demo use; do not use it as a substitute for a production database.

### 3. Start the API

Keep both database variables set in the terminal running the server:

```powershell
Set-Location backend
$env:SUPABASE_DATABASE_URL = 'sqlite:///./atlas-runtime.db'
$env:DATABASE_URL = 'sqlite:///./atlas-runtime.db'
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API base URL: `http://127.0.0.1:8000`
- Health check: `http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`

### 4. Start the frontend

Open a second PowerShell terminal at the repository root:

```powershell
Set-Location frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`. The frontend defaults to the API at `http://127.0.0.1:8000`; override it at build/runtime with the Vite variable `VITE_API_URL` if using another API URL.

## Demo accounts

After running the seed command, all demo users have the same development-only password, `demo-password`.

| Role | Email |
| --- | --- |
| Engineering Manager | `manager@finpay.demo` |
| Knowledge Holder | `arun@finpay.demo` |
| Incoming Engineer | `priya@finpay.demo` |
| Admin / CTO | `admin@finpay.demo` |

Do not use these accounts or their shared password outside a local demo environment.

## Configuration

`backend/.env.example` lists backend environment variables. Copy it to `backend/.env` and set the values required for your environment. The `.env` file is ignored by Git; never commit secrets.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection URL, or a local SQLite URL for development. |
| `SUPABASE_DATABASE_URL` | Optional PostgreSQL connection URL; when set, it takes precedence over `DATABASE_URL`. |
| `CORS_ORIGINS` | Comma-separated allowed browser origins. Defaults to local Vite origins. |
| `JWT_SECRET` | Secret used to sign JWTs. Replace the example value with a long random secret outside local demos. |
| `JWT_EXPIRE_MINUTES` | JWT expiration time in minutes. |
| `GITHUB_TOKEN` | GitHub personal/access token used by the current server-side client. Keep it on the backend. |
| `GITHUB_ORG` | GitHub organization to query. |
| `GITHUB_OWNER` | GitHub user/owner to query when not using an organization. |
| `JIRA_BASE_URL` | Jira site URL, for example `https://company.atlassian.net`. |
| `JIRA_EMAIL` | Jira account email used for basic API authentication. |
| `JIRA_API_TOKEN` | Jira API token. Keep it on the backend. |
| `JIRA_PROJECT_KEYS` | Comma-separated project keys used in Jira issue search. |
| `AI_PROVIDER` | Backend provider selected by the AgentRouter; currently `anthropic`. |
| `ANTHROPIC_AUTH_TOKEN` | AgentRouter auth token used only by the backend. |
| `ANTHROPIC_API_KEY` | Optional direct Anthropic API key fallback; never expose it to the frontend. |
| `ANTHROPIC_BASE_URL` | Optional Anthropic-compatible API URL. AgentRouter uses `https://agentrouter.org`. |
| `ANTHROPIC_MODEL` | Exact model ID sent by the provider adapter; the application does not substitute a default. |

The current implementation does not use GitHub OAuth or Jira OAuth. Do not put private credentials in frontend variables or bundle them into the client. For a local SQLite run, set both database variables explicitly as shown above, because a non-empty `SUPABASE_DATABASE_URL` overrides the local URL.

### Configure Anthropic through AgentRouter

The backend routes AI workflow calls through `app.services.agent_router.AgentRouter`, which currently selects the Anthropic provider using `AI_PROVIDER`. Provider configuration is backend-only. Set these values in `backend/.env`:

```dotenv
AI_PROVIDER=anthropic
ANTHROPIC_AUTH_TOKEN=your-real-AgentRouter-auth-token
ANTHROPIC_BASE_URL=https://agentrouter.org
ANTHROPIC_MODEL=claude-opus-4-8
```

Replace the token placeholder with the auth token issued by AgentRouter. The supplied `claude-opus-4-8` model ID is used verbatim; confirm it is enabled for that AgentRouter account. Alternatively, direct Anthropic API credentials can use `ANTHROPIC_API_KEY` with `ANTHROPIC_BASE_URL` unset. Never use a `VITE_` variable for provider credentials.

After configuring the token, restart the backend:

```powershell
Set-Location backend
..\\venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Log in as an admin to obtain a bearer token, then call `GET /api/ai/status` and `POST /api/ai/test` with `Authorization: Bearer <token>`. The test endpoint makes a minimal real routed request. A successful `/health` response alone does not verify database or AgentRouter connectivity.

## Database and migrations

The main entities currently model:

- Organizations, users, and teams.
- Services and repositories.
- Knowledge areas, knowledge gaps, source evidence, and knowledge records.
- Transitions and transition knowledge areas.
- Integrations, audit logs, and notifications.

Apply schema migrations from `backend/`:

```powershell
..\venv\Scripts\python.exe -m alembic upgrade head
```

Current migrations are in `backend/alembic/versions/`. The initial migration creates the base schema; the next migration records who submitted a knowledge record. `python -m app.seed` creates the demo organization and its seed data.

## Backend API

Authentication is bearer-token based. Except for health, login, and the current integration status route, API data routes require an `Authorization: Bearer <token>` header.

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/health` | API health status. |
| `POST` | `/api/auth/login` | Verify credentials and issue JWT. |
| `GET` | `/api/me` | Return the authenticated database user. |
| `GET` | `/api/workspace` | Return workspace metadata and last GitHub sync time; several counts are currently demo constants. |
| `GET` | `/api/integrations` | Report whether GitHub/Jira environment credentials are present. This is not an OAuth connection flow. |
| `POST` | `/api/integrations/{provider}/sync` | Call the configured GitHub/Jira summary client; restricted to manager/admin. |
| `GET` | `/api/knowledge-gaps` | List gaps for the authenticated organization. |
| `GET` | `/api/knowledge-gaps/{gap_id}` | Get a gap by title-derived slug within the authenticated organization. |
| `POST` | `/api/knowledge-gaps/{gap_id}/capture` | Save an answer as a proposed knowledge record; manager/holder only. |
| `GET` | `/api/knowledge-gaps/{gap_id}/records` | List persisted knowledge proposals and review states for the organization. |
| `POST` | `/api/knowledge-gaps/{gap_id}/records/{record_id}/validate` | Approve, reject, or request clarification; manager only. |
| `GET` | `/api/ai/status` | Admin-only Anthropic configuration state; never returns the API key. |
| `POST` | `/api/ai/test` | Admin-only minimal live Claude request. |
| `POST` | `/api/knowledge-gaps/{gap_id}/analyze` | Manager/admin analysis from organization-scoped linked evidence; persists structured output and an audit event. Requires evidence. |
| `POST` | `/api/knowledge-gaps/{gap_id}/questions` | Manager/holder generation of 1-5 targeted questions from linked evidence. |
| `POST` | `/api/knowledge-gaps/{gap_id}/structure-answer` | Structures a human answer and saves a proposed, unvalidated knowledge record. Requires evidence. |
| `GET` | `/api/github/repositories` | Manager/admin only; fetches real repositories from the configured GitHub account and upserts them into the caller's organization. |
| `GET` | `/api/github/repositories/{repository_id}/pull-requests` | Manager/admin only; fetches real recent PR metadata for a repository registered in the caller's organization. |
| `GET` | `/api/github/repositories/{repository_id}/pull-requests/{number}/evidence` | Manager/admin only; fetches PR details, changed-file patches where GitHub provides them, reviews, commits, and scoped deterministic signals. |
| `POST` | `/api/github/repositories/{repository_id}/pull-requests/{number}/analyze` | Re-fetches selected evidence server-side, routes bounded evidence/signals through AgentRouter to Claude, validates citations, and persists a positive potential gap plus evidence. |

FastAPI-generated OpenAPI documentation is available at `/docs` while the API is running.

## Frontend routes and roles

The role-based navigation preserves four product roles:

- **Manager:** overview, knowledge map, risk areas, knowledge gaps, transitions, integrations, settings.
- **Knowledge Holder:** my knowledge, knowledge gaps, pending validation, records, profile/settings.
- **Incoming Engineer:** transition, knowledge areas, knowledge checks, completed transition, profile/settings.
- **Admin:** organization, teams/members, roles/permissions, integrations, data sync, security, audit log, settings.

Routes are implemented inside `frontend/src/App.tsx`. Some pages are presentational demo views and are not yet backed by CRUD APIs. The demo-role switch in the sidebar is a frontend convenience and does not provide secure role switching; backend authorization remains the security boundary.

## Integrations

### GitHub

Set `GITHUB_TOKEN` and either `GITHUB_ORG` or `GITHUB_OWNER` on the backend. The client requests repositories, pull requests, and contributors. The sync endpoint returns summary counts and records the last sync time in the integration row after the provider calls succeed.

### Jira

Set `JIRA_BASE_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN`; optionally set `JIRA_PROJECT_KEYS`. The client requests project and issue summaries. The sync endpoint returns summary counts and records the last sync time after successful provider requests.

The generic integration sync clients remain summary-oriented and do not ingest all repository/PR/Jira records. The live GitHub Evidence workspace now fetches repository, pull request, changed-file, review, and commit details on demand; repository metadata is upserted using the existing repository entity, and selected PR evidence is persisted against a created/reused knowledge gap after a positive, validated Claude finding. GitHub pagination follows API links with a bounded page count. Jira ingestion/linkage and a general-purpose bulk sync pipeline remain unimplemented. A successful GitHub list request means those requested provider records were fetched; it does not mean all organization source data was imported.

### Live GitHub evidence demo

Open **GitHub Evidence** from the manager/admin navigation. Refresh retrieves repositories from the backend-configured GitHub namespace. Select a repository to fetch its pull requests, then select a PR to retrieve the real PR details, changed files/patches (where GitHub returns patches), reviews, commits, and repository contributor metadata. Click **Analyze with Claude** to trigger a new backend fetch and evidence-grounded AgentRouter request. The backend returns actual processing stages, deterministic signal definitions/values, validated structured analysis, verified evidence IDs, and persistence status. Only a `potential_gap=true` result creates/updates a persisted gap; a negative result is explicitly marked as not persisted as a gap. New gaps appear in the existing Knowledge Gaps list after refresh.

Contribution concentration is calculated from up to 20 recent PR authors (`high >=60%`, `moderate >=40% and <60%`, otherwise low); contributor redundancy counts GitHub contributor accounts, not knowledge or competence; review concentration is limited to review events on the selected PR; documentation coverage is a filename-extension/folder heuristic. Jira traceability, incident history, and service criticality are explicitly reported as not connected/not mapped, not inferred.

### AI evidence and human review

Claude calls use the official Anthropic SDK and configured backend model. Structured tool results are validated by Pydantic with one bounded repair attempt. Provider failures become application-level HTTP errors; logs omit keys and authorization headers. Context is assembled from the authorized gap, its service, and up to 20 linked `Evidence` rows with bounded text. Returned evidence IDs are checked against supplied source IDs before persistence. Missing evidence stops the request before calling Claude.

Gap analysis is saved on the existing `KnowledgeGap.ai_analysis` JSON field and creates an audit event. Claude-structured answers are saved as proposed knowledge records; manager review is still required to validate them. The deterministic continuity engine is not implemented and Claude is not asked to invent risk scores. Transition assistance, check generation, and answer verification helpers accept validated knowledge plus evidence, but the application currently lacks persisted transition/check APIs and does not expose those helpers as completed UI workflows.

## Tests and builds

### Backend tests

Install backend development/test dependencies and run the suite from `backend/`:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

Current tests exercise knowledge submission persistence, manager-only review, audit log entries, and organization isolation for review lookup.

AI unit/API tests mock Anthropic and do not require a real key. The live-provider test is skipped by default. To opt into it, configure both Anthropic variables and run:

```powershell
$env:RUN_AI_INTEGRATION_TESTS = 'true'
python -m pytest tests/test_ai_workflows.py -q
```

### Frontend production build

Run from `frontend/`:

```powershell
npm run build
```

This runs the TypeScript project build and Vite production bundle. There is no frontend test or lint script configured in `frontend/package.json` at present.

## Known limitations

This codebase is still a demo/MVP and is not production-ready. In particular:

- Dashboard and risk metrics, team/admin tables, knowledge-map nodes, some evidence references, and several transition statistics are hard-coded demo data.
- Transition creation, progress, and knowledge checks are currently frontend state; they are not a persisted end-to-end transition workflow.
- The general GitHub/Jira integration sync remains summary-only. The selected GitHub PR demo persists evidence only when a positive potential gap is validated; it does not bulk-ingest every PR or commit. Jira evidence linkage is not implemented.
- Integration status initially reflects whether credentials are configured, not an independently verified durable authorization. There is no OAuth connection lifecycle or secure per-organization credential storage.
- The workspace API returns demo counts, regardless of actual database totals.
- Teams, users, permissions, settings, notifications, evidence views, audit-log views, and most admin actions do not yet have complete backend operations.
- Knowledge gaps in the seeded workspace are sample/demo rows, not generated from an evidence analysis engine. Selected real GitHub PRs can now be analyzed with Claude and persisted with their evidence. Seeded gaps still have no linked source evidence for standalone analysis.
- Transition assistance and knowledge verification currently have schemas/service helpers only; there is no persisted transition/check backend workflow or connected UI path.
- The model includes several planned entities, but their existence does not mean their workflows are implemented.
- `backend/.env` may point to a remote Supabase database. If that host is unreachable, API database operations fail even if `/health` responds. Use the local SQLite setup above for an isolated demo, or configure a reachable database URL.

Use clear demo labels when showing seeded/static values. Do not use the current metrics, integrations, or transition pages to make operational or personnel decisions.

## Security notes

- Keep `backend/.env` out of version control and rotate any credential that has been exposed.
- Use a unique, long `JWT_SECRET` outside local development; the default in source is not suitable for production.
- Keep GitHub and Jira tokens on the backend only.
- Demo users share a known password; disable or replace them before exposing a deployment.
- Review organization scoping and role checks whenever adding a route. Frontend-only route hiding is not authorization.
- The current integration and data flows have not had a production security review.
