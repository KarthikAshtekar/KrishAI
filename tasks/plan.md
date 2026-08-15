# Implementation Plan: Cloud-Ready Krishi Connect

## Overview

Convert the current FastAPI demonstration into a cloud-ready, tenant-aware application that can run entirely on Google Cloud without requiring PostgreSQL or Docker on a developer PC. Until a live farmer data source is available, explicit demo identities and sample data remain available only in non-production environments.

Actual Google Cloud resources are not created by this change. The repository will contain tested application code, database migrations, CI checks, and parameterized deployment automation. Provisioning requires a Google Cloud project ID, region, billing configuration, and administrator identity.

## Architecture Decisions

- Keep FastAPI and server-rendered Jinja pages to preserve the existing product and API contracts.
- Use SQLAlchemy 2 with PostgreSQL on Cloud SQL. SQLite is an explicitly non-production fallback for local tests and demonstrations, so no local PostgreSQL installation is needed.
- Use Alembic for forward and rollback database migrations. Production schema creation must run as a deployment job, not implicitly during web-server startup.
- Use Firebase Authentication or Google Cloud Identity Platform. The backend exchanges recently issued ID tokens for secure, HTTP-only session cookies and verifies them on protected requests.
- Resolve tenant context from a verified user membership. A client-provided tenant ID is only a selector and is never trusted without a membership check.
- Persist decision cards and audit events. Remove process-global decision state because Cloud Run instances are stateless and concurrent.
- Emit structured JSON logs with request IDs. Rely on Cloud Run and Google Cloud Observability for platform metrics while exposing readiness details for application dependencies.
- Keep real data integrations optional. ThingSpeak continues to operate when configured; otherwise the application reports data unavailability or labelled demo output.
- Preserve the existing API paths where possible. New response fields are additive, and protected endpoints use one consistent error shape.

## Threat Model

### Trust boundaries

- Browser to FastAPI: untrusted forms, JSON, headers, cookies, and uploaded files.
- FastAPI to Firebase: externally issued identity tokens and session-cookie verification.
- FastAPI to Cloud SQL: tenant-owned data and audit history.
- FastAPI to ThingSpeak: untrusted third-party JSON over a fixed HTTPS endpoint.
- CI/CD to Google Cloud: deployment authority and artifact publication.

### Primary assets

- Farmer identity and tenant membership
- Farm and decision history
- API keys and database credentials
- Model artifacts and model-version evidence
- Administrative and audit actions

### Controls

- Boundary validation, upload limits, and generic server errors
- Firebase token verification and secure session cookies
- Tenant-scoped repository methods and cross-tenant denial tests
- Parameterized ORM queries and migrations
- Structured, allowlisted telemetry without tokens or raw request bodies
- Secret Manager references and short-lived CI credentials

## Dependency Graph

```text
Configuration and validation
          |
          +--> Database schema and migrations
          |          |
          |          +--> User and tenant membership
          |          |          |
          |          |          +--> Authentication and authorization
          |          |                         |
          |          +-------------------------+--> Persisted decisions and audits
          |
          +--> Request telemetry and readiness
                         |
                         +--> CI/CD and Cloud Run deployment automation
```

## Task List

### Phase 1: Stability and contracts

- [ ] Task 1: Validate model and API inputs and repair fertilizer moisture handling
- [ ] Task 2: Add deterministic API integration-test infrastructure

### Checkpoint: Stable prototype

- [ ] Existing and new tests pass
- [ ] Every API rejects invalid boundary inputs predictably
- [ ] Fertilizer recommendations work when moisture is omitted

### Phase 2: Persistence and isolation

- [ ] Task 3: Add SQLAlchemy schema and Alembic migrations
- [ ] Task 4: Add tenant-scoped repositories and cross-tenant tests
- [ ] Task 5: Add Firebase session authentication and membership authorization
- [ ] Task 6: Persist decision cards and audit events

### Checkpoint: Stateful tenant-aware application

- [ ] Database migrations upgrade and downgrade successfully
- [ ] A tenant cannot read another tenant's decision history
- [ ] Production configuration fails closed when authentication is disabled
- [ ] No runtime feature depends on process-global state

### Phase 3: Operations and delivery

- [ ] Task 7: Add structured observability, security middleware, and readiness checks
- [ ] Task 8: Add cloud deployment automation, CI gates, and operating documentation
- [ ] Task 9: Refresh and verify the canonical project explainer

### Checkpoint: Cloud-ready handoff

- [ ] Full test, lint, compile, migration, and container-build checks pass
- [ ] No secret value is present in tracked configuration
- [ ] Deployment automation is parameterized and does not create paid resources automatically
- [ ] Reader-facing documentation distinguishes implemented, configured, demo, and pending-live-data behavior

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| No live farmer data | High | Preserve explicit demo mode and design stable ingestion contracts without inventing live evidence. |
| Firebase project not configured | Medium | Keep a non-production demo identity and fail closed when `APP_ENV=production`. |
| Cloud SQL creates ongoing cost | High | Provision only after budget approval; document small development sizing and shutdown behavior. |
| Historical model artifacts use older libraries | High | Add compatibility/readiness evidence and keep provisional models labelled; avoid claiming revalidation without new data. |
| Tenant filtering is missed in one query | Critical | Centralize scoped queries and add direct cross-tenant denial tests. |
| Cloud Run instance replacement loses state | High | Persist business state in PostgreSQL and use no writable container state for durability. |
| CI credentials leak | High | Use Workload Identity Federation or Cloud Build service identity; never commit service-account keys. |

## Open Configuration Inputs

- Google Cloud project ID
- Deployment region, tentatively `asia-south1`
- Cloud SQL instance size and approved monthly budget
- Firebase/Identity Platform web configuration
- Initial administrator Firebase UID and tenant name
- Production hostname, needed for final cookie and CSP policy review
