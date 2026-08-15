# Krishi Connect

Krishi Connect is a cloud-ready agricultural decision-intelligence application for farmers, buyers, FPOs/cooperatives, and agriculture teams. It combines saved crop and fertilizer models, transparent price rules, optional ThingSpeak readings, workflow alerts, tenant-scoped decision history, and a guided assistant.

The repository is implementation-complete for a cloud handoff. Google Cloud resources are **not live yet**: provisioning requires a project ID, billing approval, Firebase web configuration, and the first administrator's Firebase UID. No local PostgreSQL installation is required.

## Current evidence boundary

| Capability | Current status |
| --- | --- |
| Crop and fertilizer recommendations | Saved scikit-learn artifacts load under their matching `1.6.1` runtime; predictive quality has not been revalidated without held-out data. |
| Price outlook | Transparent CSV lookup plus seasonal/year rules; the incomplete legacy XGBoost path is not loaded. |
| Disease inference | Disabled until class labels, preprocessing, and validation images are available. |
| IoT | ThingSpeak integration is ready when a channel/key is configured; no live farmer feed is currently connected. |
| Marketplace and community views | Clearly labelled sample data. |
| Authentication | Firebase ID-token/session-cookie flow is implemented; demo identity is allowed only outside staging/production. |
| Persistence and tenant isolation | SQLAlchemy schema, Alembic migration, scoped repositories, audit records, and cross-tenant denial tests are implemented. |
| Monitoring | JSON request logs, request IDs, readiness checks, Cloud Run metrics, and parameterized alert-policy setup are implemented/configured; alerts become live only after deployment and a notification channel are connected. |
| CI/CD | GitHub Actions quality gates and Cloud Build migration/deployment pipeline are included; neither has been run in the user's cloud account yet. |

## Application pipeline

```text
Browser or API client
  -> Firebase sign-in (production) / explicit demo identity (local only)
  -> FastAPI validation and tenant-membership resolution
  -> optional ThingSpeak normalization
  -> crop/fertilizer model wrappers + transparent price rules
  -> anomaly, explanation, action, and workflow assembly
  -> tenant-scoped PostgreSQL decision card + audit event
  -> server-rendered dashboard or JSON response
  -> structured logs and Cloud Run/Cloud SQL platform metrics
```

## Cloud architecture

```text
Firebase Authentication / Identity Platform
                 |
                 v
Public HTTPS Cloud Run service (application authentication still required)
  |              |                  |
  |              |                  +-> Cloud Logging / Monitoring
  |              +-> optional ThingSpeak HTTPS API
  +-> Cloud SQL Auth Connector socket -> Cloud SQL for PostgreSQL

Cloud Build -> Artifact Registry -> migration Cloud Run Job -> Cloud Run revision
Secret Manager -> DATABASE_URL injected into service and migration job
```

Cloud Run is allowed to receive unauthenticated HTTPS traffic because users need to reach `/login`; business pages and APIs enforce Firebase/application authentication. The runtime service account receives only Cloud SQL Client and Secret Manager accessor permissions. Database migrations run as a separate job before a new service revision is deployed.

## Local development without PostgreSQL

SQLite is built into Python and is intentionally supported for local development/tests only.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --port 8080
```

Open `http://localhost:8080`. With the example configuration, the UI shows that a non-production demo identity is active. Do not use `AUTH_MODE=demo` for a deployed environment; production configuration rejects it at startup.

## Pages and operational endpoints

| Path | Purpose |
| --- | --- |
| `/login` | Firebase email/password login or an explicit local demo-mode notice |
| `/` | Crop, fertilizer, price, and disease-status forms |
| `/decision-intelligence` | Decision card, trust layer, workflow log, and assistant |
| `/dashboard` | Optional ThingSpeak charts and anomaly alerts |
| `/farmer-dashboard` | Farmer action view |
| `/marketplace` | Sample marketplace view |
| `/community-dashboard` | Sample FPO/community view |
| `/healthz` | Process liveness only |
| `/readyz` | Database and critical-model readiness; returns `503` when unavailable |

All business APIs require a verified principal. A client may send `X-Tenant-ID` only to select among its own memberships; it cannot use the header to acquire membership.

## Configuration

Copy `.env.example`; never commit `.env`.

| Variable | Local default | Production requirement |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` |
| `AUTH_MODE` | `demo` | `firebase` |
| `DATABASE_URL` | local SQLite | Secret Manager value pointing to Cloud SQL PostgreSQL |
| `FIREBASE_PROJECT_ID` | blank | required |
| `FIREBASE_WEB_API_KEY` | blank | required web configuration; public identifier, not an admin credential |
| `FIREBASE_AUTH_DOMAIN` | blank | required |
| `THINGSPEAK_CHANNEL_ID` | demo channel ID | replace when a farmer feed is connected |
| `THINGSPEAK_READ_API_KEY` | blank | optional secret for a private channel |

The backend uses Application Default Credentials for Firebase Admin. Never download or commit a service-account JSON key for Cloud Run.

## Tests and quality gates

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m py_compile app.py auth.py config.py database.py db_models.py decision_engine.py ml_services.py observability.py repositories.py schemas.py
.\.venv\Scripts\pip-audit.exe -r requirements.txt
```

Migration verification:

```powershell
$env:DATABASE_URL = "sqlite+pysqlite:///./migration_check.db"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\alembic.exe downgrade base
```

The GitHub workflow additionally builds both Docker test and runtime stages. The runtime container runs as an unprivileged user and excludes the disabled 51 MB disease artifact and unused price pickle.

## Google Cloud deployment

Use Google Cloud Shell so no PostgreSQL, Docker, or Google Cloud CLI installation is needed on the PC. The guarded bootstrap script refuses to create paid resources unless `CONFIRM_CREATE_PAID_RESOURCES=YES` is set.

1. Create or select a billed Google Cloud project.
2. Add Firebase to that project, register a web app, and enable Email/Password authentication.
3. In Cloud Shell, clone this repository and export the required values.
4. Run `scripts/gcp_bootstrap.sh` only after reviewing Cloud SQL pricing.
5. Submit `cloudbuild.yaml` with the exact substitutions printed by the bootstrap script.
6. Create the first Firebase user, then run the tenant-bootstrap job documented in [docs/GCP_RUNBOOK.md](docs/GCP_RUNBOOK.md).
7. Verify `/healthz`, `/readyz`, sign-in, tenant access, logs, and backups before sending live traffic.

Example bootstrap environment:

```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="asia-south1"
export FIREBASE_PROJECT_ID="your-project-id"
export FIREBASE_WEB_API_KEY="your-public-web-api-key"
export FIREBASE_AUTH_DOMAIN="your-project-id.firebaseapp.com"
export CONFIRM_CREATE_PAID_RESOURCES="YES"
bash scripts/gcp_bootstrap.sh
```

Detailed provisioning, deployment, first-admin bootstrap, monitoring, rollback, backup, and teardown instructions are in [docs/GCP_RUNBOOK.md](docs/GCP_RUNBOOK.md).

## Data model

The initial migration creates:

- tenants, users, and tenant memberships;
- farms and plots;
- sensor devices and time-stamped readings;
- decision cards and audit events;
- marketplace listings and model-version records.

Every tenant-owned repository read requires `tenant_id`. Decision responses include a durable `decision_id`; automation and assistant paths load the current tenant's latest database record rather than process memory.

## Security and operations

- Production fails closed if Firebase, PostgreSQL, or Firebase web configuration is missing.
- Firebase tokens are verified by the Admin SDK; recently authenticated ID tokens are exchanged for HTTP-only session cookies.
- Session creation/logout use double-submit CSRF checks; secure cookies and HSTS are enabled in deployed environments.
- Inputs are bounded, extra JSON fields are rejected, uploads are limited to 5 MB and safe image types, and internal exception text is not exposed.
- Responses carry CSP, clickjacking, content-type, referrer, permissions, and request-ID headers.
- Logs contain bounded request metadata, not bodies, passwords, cookies, authorization headers, or tokens.
- Alembic migrations are not executed implicitly during production web startup.

## Remaining work requiring external data or human decisions

- Connect and validate the actual farmer/ThingSpeak source and define ownership/consent/retention rules.
- Recreate and validate the full price preprocessing/model pipeline.
- Supply disease class labels, preprocessing contract, representative validation images, and agronomist approval.
- Replace sample marketplace/community records with consented operational data.
- Configure notification recipients, an uptime check, budgets, production hostname, and final CSP/cookie-domain review.
- Revalidate crop/fertilizer quality on a locked representative holdout before claiming production agronomic accuracy.

The canonical business-and-technical explanation is `project_explainer.html`; it separates code-complete capabilities from cloud resources and live-data evidence that are still pending.
