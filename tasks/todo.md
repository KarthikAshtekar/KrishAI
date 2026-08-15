# Cloud Production Foundation Tasks

## Task 1: Validate inputs and repair fertilizer moisture handling

**Description:** Add explicit boundary constraints to agricultural inputs and reproduce then fix the optional-moisture failure without changing the existing successful prediction contract.

**Acceptance criteria:**

- [x] Omitting fertilizer moisture uses the documented value of 45.
- [x] Out-of-range nutrient, weather, pH, month, year, question, and crop-type values return validation errors.
- [x] Internal exceptions are not returned verbatim as HTTP 500 details.

**Verification:**

- [x] Focused regression tests fail before and pass after the repair.
- [x] `python -m unittest` passes.
- [x] `python -m py_compile app.py ml_services.py decision_engine.py` passes.

**Dependencies:** None

**Files likely touched:** `app.py`, `ml_services.py`, `tests/test_ml_services.py`, `tests/test_api.py`

**Estimated scope:** Medium

## Task 2: Add deterministic API integration-test infrastructure

**Description:** Add the repository's explicit development dependencies and an isolated API test configuration that never calls ThingSpeak or production services.

**Acceptance criteria:**

- [x] API tests run against deterministic test configuration.
- [x] External sensor calls are replaced at the boundary in tests.
- [x] Production and development dependency sets are documented.

**Verification:**

- [x] Test discovery runs all unit and API tests.
- [x] A clean dependency installation can import the application.

**Dependencies:** Task 1

**Files likely touched:** `requirements.txt`, `requirements-dev.txt`, `tests/__init__.py`, `tests/test_api.py`

**Estimated scope:** Small

## Checkpoint: Stable prototype

- [x] All tests pass.
- [x] Application imports and compiles.
- [x] Fertilizer request without moisture succeeds.

## Task 3: Add SQLAlchemy schema and Alembic migrations

**Description:** Introduce a PostgreSQL-compatible schema for tenants, users, memberships, farms, plots, devices, decision cards, marketplace listings, model versions, and audit events. SQLite remains test-only.

**Acceptance criteria:**

- [x] Schema is represented with SQLAlchemy 2 typed mappings.
- [x] Initial Alembic upgrade creates all required tables and constraints.
- [x] Migration downgrade removes only objects created by that migration.

**Verification:**

- [x] Upgrade and downgrade succeed against a temporary SQLite database.
- [x] Schema tests verify required foreign keys and uniqueness constraints.

**Dependencies:** Task 2

**Files likely touched:** `database.py`, `db_models.py`, `alembic.ini`, `migrations/`

**Estimated scope:** Medium

## Task 4: Add tenant-scoped repositories

**Description:** Centralize creation and lookup of memberships, decisions, and audit events so every business query takes an explicit tenant identifier.

**Acceptance criteria:**

- [x] Repository methods require tenant context for tenant-owned records.
- [x] Cross-tenant identifiers return no record.
- [x] Writes use transactional SQLAlchemy sessions.

**Verification:**

- [x] Repository integration tests use a real temporary SQLite database.
- [x] Cross-tenant tests prove that records cannot be read by another tenant.

**Dependencies:** Task 3

**Files likely touched:** `repositories.py`, `database.py`, `tests/test_repositories.py`

**Estimated scope:** Medium

## Task 5: Add Firebase session authentication and authorization

**Description:** Verify Firebase ID tokens or session cookies, exchange recent ID tokens for secure cookies, and resolve a verified user's tenant membership and role.

**Acceptance criteria:**

- [x] Production refuses to start with authentication disabled.
- [x] Missing, invalid, and unauthorized identities produce consistent 401 or 403 responses.
- [x] Session cookies are HTTP-only, secure in production, and protected by CSRF controls.

**Verification:**

- [x] Unit tests cover demo, Firebase-verifier failure, role denial, and tenant-membership denial.
- [x] API tests cover session creation/logout contracts without external Firebase calls.

**Dependencies:** Task 4

**Files likely touched:** `auth.py`, `app.py`, `templates/login.html`, `tests/test_auth.py`

**Estimated scope:** Medium

## Task 6: Persist decision cards and audit events

**Description:** Replace `LAST_DECISION_CARD` with tenant-scoped database storage while preserving existing decision-card, automation-log, and assistant responses.

**Acceptance criteria:**

- [x] POSTed decision cards are persisted with tenant, actor, request, result, and model-basis metadata.
- [x] GET, automation-log, and assistant paths retrieve only the current tenant's latest card.
- [x] Significant decisions and authentication actions write audit events.

**Verification:**

- [x] API integration test creates then retrieves a decision card.
- [x] A second tenant cannot retrieve the first tenant's card.
- [x] Application source contains no process-global decision cache.

**Dependencies:** Tasks 4 and 5

**Files likely touched:** `app.py`, `repositories.py`, `schemas.py`, `tests/test_api.py`

**Estimated scope:** Medium

## Checkpoint: Stateful tenant-aware application

- [x] Migrations and repository tests pass.
- [x] Authentication and authorization tests pass.
- [x] Decision workflow works across separate requests without global state.

## Task 7: Add observability, security middleware, and readiness

**Description:** Emit structured request events with correlation IDs, add safe response headers and consistent error envelopes, and separate liveness from dependency readiness.

**Acceptance criteria:**

- [x] Every response includes a request ID and baseline security headers.
- [x] Request logs contain bounded, structured fields and no body, token, or password data.
- [x] `/readyz` reports database and critical model readiness with HTTP 200 or 503.

**Verification:**

- [x] Middleware tests inspect headers, errors, and request-ID propagation.
- [x] Readiness tests cover healthy and unhealthy dependencies.

**Dependencies:** Task 6

**Files likely touched:** `observability.py`, `app.py`, `tests/test_observability.py`

**Estimated scope:** Medium

## Task 8: Add cloud deployment automation, CI, and operating documentation

**Description:** Add repeatable quality gates and parameterized Google Cloud scripts for Cloud SQL, Secret Manager, Cloud Build, migrations, and Cloud Run without embedding project-specific secrets.

**Acceptance criteria:**

- [x] CI runs lint, compile, tests, migration checks, dependency audit, and container build.
- [x] Deployment files use substitutions or environment variables for project-specific values.
- [x] Runbooks explain initial provisioning, migrations, deployment, rollback, backup, and demo/live-data status.

**Verification:**

- [x] YAML parses and shell scripts are documented for Cloud Shell; YAML passed local parsing (no local Bash runtime available).
- [ ] Docker image builds and `/healthz` responds.
- [x] Secret scan finds no real credential values.

**Dependencies:** Task 7

**Files likely touched:** `.github/workflows/ci.yml`, `cloudbuild.yaml`, `scripts/`, `README.md`

**Estimated scope:** Medium

## Task 9: Refresh the canonical project explainer

**Description:** Update the reader-facing report so implemented production foundations, configuration-dependent cloud resources, demo data, and remaining evidence gaps are accurately separated.

**Acceptance criteria:**

- [x] The report reflects authentication, persistence, isolation, monitoring, and CI/CD code now present.
- [x] No cloud resource is described as live until it has been provisioned and verified.
- [x] The canonical HTML remains self-contained and passes desktop/mobile checks.

**Verification:**

- [x] The explainer generation/verification command passes.
- [x] Every cited local source path exists.

**Dependencies:** Task 8

**Files likely touched:** `project_explainer_artifact.json`, `project_explainer.html`, `package_project_explainer.mjs`

**Estimated scope:** Medium

## Checkpoint: Cloud-ready handoff

- [ ] All quality gates pass.
- [x] No paid cloud resource was created without explicit project and budget inputs.
- [x] Remaining manual configuration is listed with exact commands and evidence boundaries.
