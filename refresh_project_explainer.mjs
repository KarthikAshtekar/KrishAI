#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const artifactPath = resolve("project_explainer_artifact.json");
const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

const replacements = {
  technical_summary: `## What the project is — and what it is not

**In business terms:** Krishi Connect is an agricultural decision-support product that brings farmer inputs, optional sensor evidence, model recommendations, transparent alerts, market context, and follow-up actions into one accountable Decision Card. The repository is now implementation-complete for a cloud handoff: identity, durable history, tenant isolation, auditability, monitoring hooks, and delivery automation are present.

**In technical terms:** it is a FastAPI/Jinja application with Firebase session authentication, SQLAlchemy 2 persistence, Alembic migrations, tenant-scoped repositories, scikit-learn model wrappers, a deterministic decision engine, structured JSON telemetry, GitHub Actions checks, and a Cloud Build pipeline for Cloud SQL migrations and Cloud Run deployment. Local development uses built-in SQLite, so PostgreSQL does not need to be installed on the PC.

**What is not complete externally:** no Google Cloud resource has been provisioned from this checkout, no Firebase project or first administrator is connected, and no authorized live farmer feed is available. Crop/fertilizer artifacts load under their matching runtime, but model quality has not been revalidated on a representative locked holdout. Price remains a transparent rule fallback, disease inference remains disabled, and marketplace/community records remain samples.

**Maturity verdict:** the software foundation is suitable for a controlled cloud pilot after configuration and verification. It is not yet evidence for production agronomic accuracy, farmer impact, a live marketplace, or a live multi-farm operation.`,

  evidence_boundary: `## The honesty map separates implemented code from live operational evidence

| Evidence class | Current capability | What a business reader should conclude |
|---|---|---|
| Implemented and locally tested | Firebase session flow, CSRF, fail-closed production configuration, PostgreSQL-compatible schema, migrations, tenant filtering, persistent decisions/audits, readiness, structured logs, CI/CD definitions | The production foundation exists in code and its local/test contracts pass. |
| Configuration-dependent | Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Cloud Build deployment, alert policies | Parameterized automation is ready, but these services are not live until the owner supplies a GCP project, billing approval, Firebase configuration, and notification channel. |
| Model-based | Crop and fertilizer recommendations | Saved classifiers load and infer under scikit-learn 1.6.1; field performance and calibration remain unverified. |
| Live if configured | ThingSpeak sensor reads | Telemetry can be real only after the farmer-owned channel, field mapping, consent, units, and freshness are verified. |
| Rule-based | Anomalies, risk, workflow actions, assistant intents | Outputs are explainable thresholds/keywords—not learned risk probabilities or a generative AI agent. |
| Demo fallback/data | Price outlook, marketplace listings, community aggregation | Useful for workflow demonstration, not commercial or impact decisions. |
| Disabled | Disease inference | A model file exists, but labels and validated preprocessing are absent; the runtime image excludes it. |

The application is called **Krishi Connect** in code and **Krishi AI** in the original presentation. This explainer treats them as one project lineage and uses current code/tests as authority.`,

  runtime_pipeline: `## Runtime pipeline: identity and farm inputs become a durable, explainable action card

\`\`\`text
Browser/API -> Firebase ID token -> recent-token session exchange -> HTTP-only cookie
     |                CSRF check + token verification + membership lookup
     v
Pydantic boundary validation -> tenant-scoped request context + request ID
     |
     +-> farmer N/P/K, pH, weather, crop/soil inputs
     +-> optional ThingSpeak readings -> cleaning, type normalization, freshness rules
     |
     v
Crop Random Forest + Fertilizer Random Forest + transparent price fallback
     |
     v
Decision engine -> anomaly severity -> trust cards -> recommended actions -> workflow log
     |
     v
SQL transaction -> decision_cards + audit_events, both keyed by verified tenant
     |
     +-> HTML/JSON response with decision_id
     +-> structured request log + Cloud Run/Cloud SQL platform metrics
\`\`\`

**Business reading:** each recommendation has an owner, tenant, evidence basis, durable identifier, and audit trail. A page refresh or Cloud Run instance replacement does not erase the latest decision.

**Technical reading:** authentication never trusts a tenant header by itself; the header only selects an active membership. Repository reads require tenant context. Cloud Run instances remain stateless while Cloud SQL owns durable business records.`,

  offline_training_pipeline: `## Offline training and online serving are separate pipelines

\`\`\`text
CSV -> notebook cleaning/features -> train/test evaluation -> serialized artifacts
    -> pinned serving runtime -> feature-contract wrapper -> readiness check -> predict()
\`\`\`

The notebooks are the model-development record; FastAPI is the online inference path. The serving image includes only required artifacts and price reference data. scikit-learn is pinned to 1.6.1 to align with the saved crop/fertilizer artifacts. The unused legacy XGBoost price pickle is excluded and not loaded because its fitted encoder/scaler pipeline is missing. This removes a misleading compatibility path, but does not substitute for prediction-parity and external-quality validation.`,

  fertilizer_model: `### Notebook score, saved model, and repaired runtime contract

The notebook creates a 441-row training set and 111-row test set, then fits a random forest. A 3-fold grid search evaluates 81 parameter combinations (243 fits); the saved best settings include 100 trees and maximum depth 10. The notebook reports 1.00 test accuracy and a 0.9932 best cross-validation score. Because 75% of dataset rows are exact duplicates, these remain leakage-sensitive development diagnostics.

The model and three encoders load under the pinned runtime. The earlier omitted-moisture failure is repaired: missing or explicit-null moisture now uses the documented value of **45**, and regression/API tests cover the path. This makes the endpoint operational, but agronomic validity still depends on deduplicated evaluation, representative geography/season coverage, and field review.`,

  decision_trust_assistant: `## The Decision Card is now a durable tenant-scoped integration record

Each card combines recommendations, sensor/anomaly status, market context, trust explanations, and workflow actions. POST writes the input payload, result, actor, request ID, model-basis metadata, and tenant to \`decision_cards\`; a paired \`audit_events\` record captures the significant action. GET, automation, and assistant paths retrieve only the verified tenant's latest card.

The assistant remains intentionally bounded. It classifies common intents with keywords and answers from the latest decision/anomaly context. It does not call a generative model, invent missing farmer data, or acquire access outside the current tenant. This is safer and cheaper for a pilot, though it is not open-ended conversational intelligence.`,

  interfaces: `## Interfaces: eight pages and protected APIs share one FastAPI service

| Surface | Purpose | Access/evidence status |
|---|---|---|
| \`/login\` | Firebase email/password sign-in; session-cookie exchange | Public entry; demo bypass is visibly labelled and only allowed outside staging/production |
| \`/\` | Crop, fertilizer, price, and disease-status forms | Authenticated business page |
| \`/decision-intelligence\` | Decision Card, trust layer, workflows, assistant | Authenticated; decisions are persistent and tenant-scoped |
| \`/dashboard\` | ThingSpeak charts and anomalies | Authenticated; live only when farmer data is configured |
| \`/farmer-dashboard\` | Farmer operating view | Authenticated |
| \`/marketplace\` | Buyer-connect demonstration | Authenticated; sample data |
| \`/community-dashboard\` | FPO/community aggregation | Authenticated; sample data |
| \`/disease-prediction\` | Safe disabled-state workflow | Authenticated; uploads capped at 5 MB and restricted to JPEG/PNG/WebP |
| \`/healthz\` / \`/readyz\` | Liveness / database-and-model readiness | Public operational probes; readiness returns 503 on dependency failure |

Protected responses use a consistent additive error envelope and carry request ID plus baseline CSP, clickjacking, content-type, referrer, and permissions headers.`,

  verification: `## Verification performed after the production-foundation implementation

**Passed locally:**

- **61** discovered unit/integration tests, including validation, missing moisture, authentication/CSRF, environment fail-closed and secure-cookie checks, token/upstream-secret redaction, session membership denial, role denial, migration parity, upgrade/downgrade, tenant isolation, cross-request decision persistence, audit writes, readiness, headers, logging redaction, and idempotent first-tenant bootstrap.
- Ruff repository lint and Python compile checks.
- Alembic upgrade, metadata check, and downgrade against temporary SQLite databases.
- Crop/fertilizer artifact loading under scikit-learn 1.6.1 with all readiness components true.
- Dependency audit: no known vulnerabilities reported for the pinned runtime requirements at verification time.
- GitHub Actions and Cloud Build YAML parse; no credential-shaped tracked values found.

**Browser/report QA:** the self-contained explainer is generated and checked in desktop/mobile modes by the portable-report verifier. The login page is also exercised locally in an isolated browser after generation.

**Not verified in this checkout:** Docker build, because Docker is intentionally not installed on the low-space PC; the included CI and Cloud Build pipelines perform it. Also unverified are a live GCP revision, Cloud SQL connectivity, real Firebase login, notification delivery, private ThingSpeak access, device-to-field mapping, load/concurrency, and agricultural impact.`,

  hosting_mental_model: `## Hosting explained plainly: every cloud component has one job

A useful mental model is a managed restaurant:

- **Git repository** is the recipe and audit history.
- **Cloud Build** is the inspected kitchen that runs tests and builds a sealed image.
- **Artifact Registry** is the versioned shelf holding that image.
- **Cloud Run** opens or closes serving stations as traffic changes; stations keep no durable farm history.
- **Cloud SQL for PostgreSQL** is the durable ledger for tenants, decisions, and audits.
- **Firebase Authentication** proves who the user is; database membership decides which tenant they may use.
- **Secret Manager** supplies the database connection without putting passwords in code or image layers.
- **Cloud Logging/Monitoring** records requests and platform health and routes alerts after a human notification channel is configured.

\`\`\`text
Git push/manual submit -> Cloud Build tests -> runtime image -> Artifact Registry
                                      |
                                      v
                           migration Cloud Run Job
                                      |
                                      v
Browser -> HTTPS -> Cloud Run revision -> Cloud SQL socket
    |              |        |              |
Firebase login ----+        +-> ThingSpeak (optional)
                            +-> JSON logs / managed metrics
\`\`\`

No PostgreSQL or Docker installation is required on the PC: development uses SQLite, and builds/provisioning run in Google Cloud/GitHub infrastructure.`,

  hosting_repo_specific: `## What this repository's container and deployment pipeline do

The multi-stage Dockerfile has a test target and a smaller runtime target. The test stage installs development tools and executes lint/tests. The runtime stage uses Python 3.11, exact dependencies, a non-root user, only application/migration assets, required model artifacts, and the small price CSV. It excludes notebooks, the disabled 51 MB disease model, the unused XGBoost pickle, presentation/report files, local databases, logs, and virtual environments.

\`cloudbuild.yaml\` then performs six ordered actions: container tests, runtime build, Artifact Registry push, migration-job update, blocking Alembic migration execution, and Cloud Run deployment. If tests or migrations fail, the new application revision is not deployed.`,

  hosting_command: `## Cloud provisioning and deployment are intentionally two separate approvals

**Provisioning:** \`scripts/gcp_bootstrap.sh\` runs in Google Cloud Shell and refuses to create anything until \`CONFIRM_CREATE_PAID_RESOURCES=YES\`. It enables APIs, creates Artifact Registry, a least-privilege runtime service account, a small PostgreSQL 16 Cloud SQL instance, database/user, Secret Manager database URL, and scoped Cloud Build permissions. Cloud SQL is the main continuously billed component.

**Deployment:** the owner submits \`cloudbuild.yaml\` with project/region, immutable image tag, Cloud SQL connection, runtime identity, Firebase web configuration, and secret names. The application uses \`APP_ENV=production\` and \`AUTH_MODE=firebase\`; startup fails if Firebase or PostgreSQL configuration is absent.

**First user:** after Firebase creates the administrator identity, a one-time Cloud Run Job runs \`python -m scripts.bootstrap_tenant\` with that UID. It creates or updates the tenant, user, and ADMIN membership idempotently.

Every command and rollback/backup step is in \`docs/GCP_RUNBOOK.md\`. No paid resource was created while producing this report.`,

  cloud_runtime: `## What happens after deployment: revisions scale, the database persists, and readiness exposes failures

Cloud Run creates an immutable revision for each image/config combination and is configured with zero minimum instances, at most three instances, one CPU, 1 GiB memory, concurrency 40, and a 60-second request timeout. Scale-to-zero reduces idle compute cost but can add cold-start delay. Cloud SQL does not scale to zero and continues billing while the instance exists.

The public Cloud Run URL is necessary for the login page, but application routes still enforce Firebase and membership authorization. \`/healthz\` says the process is alive. \`/readyz\` tests database connectivity and critical model/reference loading; it returns HTTP 503 if either is unavailable. Durable cards/audits remain in PostgreSQL when revisions restart or scale horizontally.`,

  cloud_security_ops: `## Cloud security, secrets, monitoring, backup, and rollback

- **Identity:** Firebase Admin verifies ID tokens/session cookies; recent sign-in is required for cookie exchange. Production has no demo fallback.
- **Authorization:** tenant selection is checked against active database membership; direct cross-tenant repository reads return no record.
- **Secrets:** Cloud Run and migration jobs receive \`DATABASE_URL\` from Secret Manager; no service-account key or real credential is tracked.
- **Web controls:** HTTP-only secure production sessions, SameSite cookies, double-submit CSRF, HSTS in deployed mode, CSP/security headers, bounded uploads, generic internal errors.
- **Observability:** structured request events contain request ID, method, bounded path, status, and duration—never bodies, authorization headers, cookies, or passwords. Cloud Run supplies request/latency/CPU/memory metrics. A guarded script creates 5xx, CPU, and memory alerts once a notification channel exists.
- **Delivery:** GitHub CI runs lint, compile, tests, migrations, dependency audit, and Docker targets. Cloud Build performs deployment-side container tests and migrations.
- **Recovery:** the runbook covers automated/on-demand Cloud SQL backups, traffic rollback to a known revision, schema compatibility review, and explicit cost-aware teardown.

Cloud configuration is code-ready, not live evidence. Notification recipients, uptime check, production domain, final cookie/CSP review, and rollback drill require the deployed environment.`,

  production_gaps: `## Remaining risk register — ordered by what can still invalidate trust

| Priority | Risk still open | Why it matters | Required closure evidence |
|---|---|---|---|
| 1 | No authorized live farmer source | Demo/default inputs cannot establish operational value or data rights | Farmer/FPO agreement, device registry, mapping, units, freshness, consent, retention tests |
| 2 | Crop/fertilizer external quality unverified | Artifact loading is not proof of field generalization | Deduplicated grouped/time/geographic holdout, calibration, agronomist review, outcome follow-up |
| 3 | Cloud/Firebase not provisioned | Production controls exist only as code until connected | Successful Cloud Build, migration job, readyz, real sign-in, tenant denial, backup and rollback evidence |
| 4 | Price is not model inference | Commercial recommendations could be mistaken for forecasts | Saved end-to-end pipeline, richer market features, locked temporal evaluation, uncertainty |
| 5 | Disease inference unavailable | A wrong disease label could cause harmful treatment | Versioned labels/preprocessing, representative images, abstention and expert escalation |
| 6 | Marketplace/community use samples | No proof of supply, buyer quality, contracts, or multi-farm aggregation | Verified actors/listings, workflow ownership, privacy and reconciliation controls |
| 7 | Alert thresholds are generic | Crop/stage/soil differences can create false urgency | Pilot-specific thresholds, false-alert review, overrides, safe advisory/actuator separation |

Authentication, persistence, tenant isolation, baseline monitoring, and CI/CD are no longer missing code paths; they remain deployment/configuration evidence to verify in the target account.`,

  roadmap: `## Future scope: move from cloud-ready code to measured agricultural outcomes

### Gate 1 — Connect the owner-controlled cloud environment

1. Approve region, Cloud SQL size, monthly budget, retention, and notification recipients.
2. Configure Firebase web authentication and the first administrator UID.
3. Run guarded bootstrap, Cloud Build, migration, tenant bootstrap, readiness, sign-in, isolation, backup, alert, and rollback checks.
4. Attach a production hostname and complete cookie/CSP/privacy review.

### Gate 2 — Connect one controlled farmer/FPO pilot

1. Register farm, plot, device, ownership, consent, field mapping, units, and data-quality rules.
2. Keep marketplace/community features labelled demo until verified operational records replace samples.
3. Measure freshness, request latency, recommendation acceptance, override rate, false urgent alerts, and follow-up completion.
4. Keep advice human-reviewed; do not connect automated pumps without a separate fail-safe control design.

### Gate 3 — Rebuild model evidence

1. Deduplicate fertilizer data and use farm/geography/time groups with an untouched external test set.
2. Rebuild price as one fitted preprocessing-and-model pipeline with temporal evaluation and uncertainty.
3. Add artifact hashes, feature-contract parity, version registry, drift/data-quality monitoring, calibration, and subgroup reporting.
4. Enable disease inference only after labels, preprocessing, representative validation, abstention, and agronomist escalation are verified.

### Gate 4 — Scale only after pilot evidence

- Multilingual, low-bandwidth/offline-first flows and assisted onboarding.
- Verified FPO/buyer workflows, logistics, quality grades, contracts, and privacy-preserving aggregation.
- Prospective evaluation of water, yield, input cost, and farmer income with uncertainty and counterfactual design.`,

  demo_flow: `## Recommended demonstration and release-review flow

1. Open \`/login\` and point out the explicit local demo banner; explain that production refuses demo authentication.
2. Submit crop and fertilizer examples, including fertilizer without moisture, and show the model basis and documented default.
3. Create a Decision Card, refresh, and show the same durable \`decision_id\`; then show the workflow/audit context.
4. Explain \`/dashboard\` as ThingSpeak-ready but not live-farmer evidence until ownership/mapping are verified.
5. Ask the assistant “What data is this based on?” to show its evidence-bounded behavior.
6. Show marketplace/community only after stating that records are samples; show disease as intentionally disabled.
7. Open \`/readyz\`, then walk through Cloud Build -> migration job -> Cloud Run -> Cloud SQL -> logs/alerts/rollback.
8. End with the honest boundary: software controls are built; cloud activation, live data, and field outcomes still require owner inputs and verification.`,

  file_map: `## Repository map: where the production-ready foundation lives

| Area | Files | Responsibility |
|---|---|---|
| Web/orchestration | \`app.py\`, \`schemas.py\` | Pages/APIs, validation, ThingSpeak boundary, decision persistence, health/readiness, auth endpoints |
| Identity/config | \`auth.py\`, \`config.py\`, \`templates/login.html\` | Firebase Admin verification, session/CSRF, principal/role resolution, fail-closed settings, login UX |
| Persistence | \`database.py\`, \`db_models.py\`, \`repositories.py\` | SQLAlchemy sessions, PostgreSQL-compatible schema, tenant-scoped queries and writes |
| Migrations | \`alembic.ini\`, \`migrations/\` | Versioned schema upgrade/downgrade; production job contract |
| Model serving | \`ml_services.py\` | Artifact loading/readiness, crop/fertilizer inference, price fallback, disabled disease status |
| Decision logic | \`decision_engine.py\` | Sensor normalization, anomaly/risk rules, trust cards, workflows, samples, assistant intents |
| Data/model development | \`Jupyter files/\`, \`models/\` | Training notebooks/CSVs and saved artifacts; incomplete artifacts excluded from runtime image |
| Observability/security | \`observability.py\` | JSON logs, request IDs, security headers, safe error envelope |
| Delivery | \`Dockerfile\`, \`.dockerignore\`, \`.github/workflows/ci.yml\`, \`cloudbuild.yaml\` | Multi-stage container, CI gates, migration-first Cloud Run delivery |
| Cloud operations | \`scripts/\`, \`docs/GCP_RUNBOOK.md\`, \`.env.example\` | Guarded provisioning/monitoring, first tenant, configuration, backup/rollback/cost controls |
| Verification | \`tests/\`, \`requirements-dev.txt\`, \`pyproject.toml\` | 61 local tests, lint rules, API/repository/auth/migration/operations contracts |

\`project_explainer.html\` is the canonical portable explainer. \`project_explainer_artifact.json\` is the auditable source, and the two Node scripts refresh/package it.`,

  next_questions: `## Inputs needed to activate the cloud release

1. What is the billed Google Cloud project ID and approved region?
2. What Cloud SQL monthly budget/tier is approved, and who receives billing/incident alerts?
3. What are the Firebase project ID, web API key, auth domain, and first administrator UID/email?
4. What production hostname and privacy/retention policy should apply?
5. Which farmer/FPO owns the first ThingSpeak channel, and what do fields 1–5 mean in units and device/plot identity?
6. Who reviews agronomic recommendations and overrides during the pilot, and which outcomes are recorded?

**Bottom line:** authentication, PostgreSQL persistence, tenant isolation, request monitoring, migrations, CI/CD, and cloud runbooks are implemented. The honest remaining boundary is external: activate them in the owner's cloud account, connect authorized farmer data, and validate agricultural outcomes before production claims.`
};

for (const [id, body] of Object.entries(replacements)) {
  const block = artifact.manifest.blocks.find((candidate) => candidate.id === id);
  if (!block) throw new Error(`Missing explainer block: ${id}`);
  block.body = body;
}

const generatedAt = new Date().toISOString();
artifact.manifest.description =
  "A source-backed business and technical walkthrough of Krishi Connect, its model/runtime pipelines, tenant-aware production foundation, detailed Google Cloud hosting architecture, evidence limits, and future scope.";
artifact.manifest.generatedAt = generatedAt;
artifact.snapshot.generatedAt = generatedAt;
artifact.snapshot.status = "ready";

const implementationSources = [
  { id: "auth", label: "Firebase authentication and authorization", path: "auth.py" },
  { id: "config", label: "Fail-closed environment configuration", path: "config.py" },
  { id: "database", label: "SQLAlchemy engine and transaction boundaries", path: "database.py" },
  { id: "db_models", label: "Tenant-aware SQLAlchemy schema", path: "db_models.py" },
  { id: "repositories", label: "Tenant-scoped persistence queries", path: "repositories.py" },
  { id: "migrations", label: "Initial Alembic migration", path: "migrations/versions/0001_cloud_schema.py" },
  { id: "observability", label: "Request telemetry and security middleware", path: "observability.py" },
  { id: "ci", label: "GitHub Actions quality gates", path: ".github/workflows/ci.yml" },
  { id: "cloudbuild", label: "Migration-first Cloud Build deployment", path: "cloudbuild.yaml" },
  { id: "runbook", label: "Google Cloud provisioning and operations runbook", path: "docs/GCP_RUNBOOK.md" },
  { id: "auth_tests", label: "Authentication and session tests", path: "tests/test_auth.py" },
  { id: "tenant_tests", label: "Cross-tenant repository tests", path: "tests/test_repositories.py" },
  { id: "persistence_tests", label: "Decision persistence API tests", path: "tests/test_decision_persistence.py" },
  { id: "cloud_sql_run", label: "Google Cloud - connect Cloud Run to Cloud SQL", href: "https://cloud.google.com/sql/docs/postgres/connect-run" },
  { id: "firebase_sessions", label: "Firebase - manage session cookies", href: "https://firebase.google.com/docs/auth/admin/manage-cookies" },
  { id: "cloud_monitoring", label: "Google Cloud - Cloud Run monitoring", href: "https://cloud.google.com/run/docs/monitoring-overview" },
  { id: "cloud_build_run", label: "Google Cloud - deploy Cloud Run with Cloud Build", href: "https://cloud.google.com/build/docs/deploying-builds/deploy-cloud-run" }
];

function mergeSources(existing) {
  const merged = new Map(existing.map((source) => [source.id, source]));
  for (const source of implementationSources) merged.set(source.id, source);
  return [...merged.values()];
}

artifact.manifest.sources = mergeSources(artifact.manifest.sources || []);
artifact.sources = mergeSources(artifact.sources || []);

writeFileSync(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
process.stdout.write(`Refreshed ${artifactPath} at ${generatedAt}\n`);
