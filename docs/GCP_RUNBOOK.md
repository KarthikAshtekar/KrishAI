# Google Cloud Runbook

This runbook deploys Krishi Connect without installing PostgreSQL or Docker locally. Run the cloud commands in Google Cloud Shell. Commands are templates: replace every placeholder and review current Google Cloud pricing first.

## 1. Required inputs

- billed Google Cloud project ID;
- deployment region (default `asia-south1`);
- Firebase web app configuration;
- Firebase UID and email for the first administrator;
- Monitoring notification-channel resource name;
- approved Cloud SQL size and budget.

The supplied bootstrap uses a `db-f1-micro` shared-core PostgreSQL 16 Enterprise instance for development cost control. Shared-core instances have no Cloud SQL SLA and are not an automatic production sizing recommendation.

## 2. Firebase setup

In Firebase Console for the same Google Cloud project:

1. Add Firebase to the project.
2. Register a web application and record `projectId`, `apiKey`, and `authDomain`.
3. Enable Authentication > Sign-in method > Email/Password.
4. Enable email-enumeration protection and set a tight Identity Toolkit sign-in quota before public access.
5. Create the initial administrator and copy its Firebase UID.

The web API key identifies Firebase configuration; it is not a Firebase Admin private key. Cloud Run uses its service identity and Application Default Credentials for Admin SDK verification.

## 3. Guarded infrastructure bootstrap

```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="asia-south1"
export FIREBASE_PROJECT_ID="your-project-id"
export FIREBASE_WEB_API_KEY="your-public-web-api-key"
export FIREBASE_AUTH_DOMAIN="your-project-id.firebaseapp.com"
export CONFIRM_CREATE_PAID_RESOURCES="YES"
bash scripts/gcp_bootstrap.sh
```

The script enables APIs, creates Artifact Registry, a least-privilege runtime service account, Cloud SQL, the application database/user, and a Secret Manager version containing the encoded socket `DATABASE_URL`. It does not deploy the app. It prints the exact Cloud Build substitutions.

Before continuing, set a Cloud Billing budget and alerts in Billing > Budgets & alerts. Budget alerts notify; they do not automatically cap charges.

## 4. Build, migrate, and deploy

Use the values printed by the bootstrap script. Choose a unique immutable image tag.

```bash
IMAGE_TAG="$(date -u +%Y%m%d-%H%M%S)"
gcloud builds submit \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --config cloudbuild.yaml \
  --substitutions "_REGION=$GCP_REGION,_AR_REPOSITORY=krishi-connect,_SERVICE_NAME=krishi-connect,_IMAGE_TAG=$IMAGE_TAG,_MIGRATION_JOB=krishi-connect-migrate,_RUNTIME_SERVICE_ACCOUNT=krishi-connect-runtime@$GCP_PROJECT_ID.iam.gserviceaccount.com,_CLOUD_SQL_CONNECTION=$GCP_PROJECT_ID:$GCP_REGION:krishi-connect-db,_DATABASE_URL_SECRET=krishi-database-url,_FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID,_FIREBASE_WEB_API_KEY=$FIREBASE_WEB_API_KEY,_FIREBASE_AUTH_DOMAIN=$FIREBASE_AUTH_DOMAIN,_THINGSPEAK_CHANNEL_ID=2914283" \
  .
```

Order is enforced: container tests, runtime build/push, migration-job configuration, `alembic upgrade head`, and only then Cloud Run deployment. A migration failure prevents the new service revision from being deployed.

Cloud Run ingress is public so `/login` is reachable. Business routes remain protected by Firebase session verification and database membership authorization.

## 5. Bootstrap the first tenant administrator

```bash
IMAGE="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT_ID/krishi-connect/krishi-connect:$IMAGE_TAG"
gcloud run jobs deploy krishi-connect-bootstrap \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --image "$IMAGE" \
  --service-account "krishi-connect-runtime@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --set-cloudsql-instances "$GCP_PROJECT_ID:$GCP_REGION:krishi-connect-db" \
  --set-secrets "DATABASE_URL=krishi-database-url:latest" \
  --command python \
  --args=-m,scripts.bootstrap_tenant,--firebase-uid=YOUR_FIREBASE_UID,--email=YOUR_EMAIL,--display-name=YOUR_NAME,--tenant-slug=first-fpo,--tenant-name=First_FPO,--role=ADMIN \
  --max-retries 0

gcloud run jobs execute krishi-connect-bootstrap \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --wait
```

The command is idempotent for the same tenant slug and Firebase UID. Spaces in argument values are awkward in Cloud Run CLI argument lists; use hyphens/underscores for the first run or update display names later through an administrative workflow.

## 6. Verify the release

```bash
SERVICE_URL="$(gcloud run services describe krishi-connect --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format 'value(status.url)')"
curl -fsS "$SERVICE_URL/healthz"
curl -fsS "$SERVICE_URL/readyz"
```

Then verify in an isolated browser:

1. `/login` loads without console errors.
2. The administrator can sign in.
3. A decision card can be created and retrieved after a page refresh.
4. An unknown or non-member Firebase user receives `403`.
5. Logs include the response `X-Request-ID` and contain no tokens.

## 7. Optional live ThingSpeak configuration

Do this only after the farmer/channel owner authorizes access and the field mapping is verified.

```bash
printf '%s' "$THINGSPEAK_READ_API_KEY" | gcloud secrets create krishi-thingspeak-read-key --data-file=- --replication-policy=automatic
gcloud run services update krishi-connect \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --update-secrets THINGSPEAK_READ_API_KEY=krishi-thingspeak-read-key:latest \
  --update-env-vars THINGSPEAK_CHANNEL_ID=YOUR_CHANNEL_ID
```

If the secret already exists, add a new version rather than running `secrets create` again. Validate timestamp freshness, units, missing-value policy, device-to-plot ownership, and consent before describing the feed as live farmer data.

## 8. Monitoring and alerting

Cloud Run automatically supplies request count, latency, instance, CPU, and memory metrics. The app adds structured request logs, request IDs, `/healthz`, and dependency-aware `/readyz`.

Create an email, SMS, Slack, or PagerDuty notification channel in Cloud Monitoring, then run:

```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="asia-south1"
export CLOUD_RUN_SERVICE="krishi-connect"
export NOTIFICATION_CHANNEL="projects/YOUR_PROJECT/notificationChannels/YOUR_CHANNEL"
export CONFIRM_CREATE_MONITORING="YES"
bash scripts/gcp_monitoring.sh
```

The script creates idempotent baseline policies for sustained 5xx responses, high memory, and high CPU. After the service URL is known, add a public HTTPS uptime check against `/readyz`; review thresholds after collecting normal traffic for at least a week.

Useful Logs Explorer filter:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="krishi-connect"
jsonPayload.event="http_request_completed"
```

## 9. Database backup and migration rollback

The bootstrap enables automated backups. Before a risky migration, create an on-demand backup:

```bash
gcloud sql backups create --instance krishi-connect-db --project "$GCP_PROJECT_ID"
```

Alembic downgrade is available, but a destructive migration rollback must be reviewed against the migration file and a fresh backup. Never assume an application traffic rollback also reverses the database.

## 10. Application rollback

List revisions:

```bash
gcloud run revisions list --service krishi-connect --region "$GCP_REGION" --project "$GCP_PROJECT_ID"
```

Move traffic to the last known-good revision:

```bash
gcloud run services update-traffic krishi-connect \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID" \
  --to-revisions LAST_KNOWN_GOOD_REVISION=100
```

Do not roll traffic back across an incompatible database migration until the schema compatibility is assessed.

## 11. Cost control and teardown

Cloud Run is configured with zero minimum instances, but Cloud SQL continues to incur charges while it exists. To stop all ongoing database charges, export any required data and delete the exact named instance only after approval:

```bash
gcloud sql instances delete krishi-connect-db --project "$GCP_PROJECT_ID"
```

That deletion is destructive. Backups, Secret Manager versions, Artifact Registry images, Cloud Run revisions/jobs, and monitoring policies have separate retention/cost behavior and should be reviewed individually.
