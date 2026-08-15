#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${FIREBASE_PROJECT_ID:?Set FIREBASE_PROJECT_ID}"
: "${FIREBASE_WEB_API_KEY:?Set FIREBASE_WEB_API_KEY}"
: "${FIREBASE_AUTH_DOMAIN:?Set FIREBASE_AUTH_DOMAIN}"

GCP_REGION="${GCP_REGION:-asia-south1}"
AR_REPOSITORY="${AR_REPOSITORY:-krishi-connect}"
CLOUD_SQL_INSTANCE="${CLOUD_SQL_INSTANCE:-krishi-connect-db}"
DATABASE_NAME="${DATABASE_NAME:-krishi_connect}"
DATABASE_USER="${DATABASE_USER:-krishi_app}"
DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-krishi-database-url}"
RUNTIME_SERVICE_ACCOUNT_NAME="${RUNTIME_SERVICE_ACCOUNT_NAME:-krishi-connect-runtime}"
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

if [[ "${CONFIRM_CREATE_PAID_RESOURCES:-NO}" != "YES" ]]; then
  echo "Refusing to create cloud resources. Review pricing, then set CONFIRM_CREATE_PAID_RESOURCES=YES."
  exit 2
fi

if [[ -z "${DATABASE_PASSWORD:-}" ]]; then
  read -r -s -p "Database password: " DATABASE_PASSWORD
  echo
fi
if [[ -z "${DATABASE_PASSWORD}" ]]; then
  echo "DATABASE_PASSWORD cannot be empty."
  exit 2
fi

gcloud projects describe "${GCP_PROJECT_ID}" >/dev/null
gcloud config set project "${GCP_PROJECT_ID}"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  monitoring.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com

if ! gcloud artifacts repositories describe "${AR_REPOSITORY}" --location "${GCP_REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${AR_REPOSITORY}" \
    --location "${GCP_REGION}" \
    --repository-format docker \
    --description "Krishi Connect application images"
fi

if ! gcloud iam service-accounts describe "${RUNTIME_SERVICE_ACCOUNT}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${RUNTIME_SERVICE_ACCOUNT_NAME}" \
    --display-name "Krishi Connect Cloud Run runtime"
fi

for role in roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member "serviceAccount:${RUNTIME_SERVICE_ACCOUNT}" \
    --role "${role}" \
    --quiet >/dev/null
done

if ! gcloud sql instances describe "${CLOUD_SQL_INSTANCE}" >/dev/null 2>&1; then
  gcloud sql instances create "${CLOUD_SQL_INSTANCE}" \
    --database-version POSTGRES_16 \
    --edition ENTERPRISE \
    --tier db-f1-micro \
    --region "${GCP_REGION}" \
    --storage-size 10 \
    --storage-auto-increase \
    --backup-start-time 18:30
fi

if ! gcloud sql databases describe "${DATABASE_NAME}" --instance "${CLOUD_SQL_INSTANCE}" >/dev/null 2>&1; then
  gcloud sql databases create "${DATABASE_NAME}" --instance "${CLOUD_SQL_INSTANCE}"
fi

if gcloud sql users list --instance "${CLOUD_SQL_INSTANCE}" --format "value(name)" | grep -Fxq "${DATABASE_USER}"; then
  gcloud sql users set-password "${DATABASE_USER}" \
    --instance "${CLOUD_SQL_INSTANCE}" \
    --password "${DATABASE_PASSWORD}"
else
  gcloud sql users create "${DATABASE_USER}" \
    --instance "${CLOUD_SQL_INSTANCE}" \
    --password "${DATABASE_PASSWORD}"
fi

CLOUD_SQL_CONNECTION="$(gcloud sql instances describe "${CLOUD_SQL_INSTANCE}" --format 'value(connectionName)')"
ENCODED_PASSWORD="$(DATABASE_PASSWORD="${DATABASE_PASSWORD}" python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["DATABASE_PASSWORD"], safe=""))')"
DATABASE_URL="postgresql+psycopg://${DATABASE_USER}:${ENCODED_PASSWORD}@/${DATABASE_NAME}?host=/cloudsql/${CLOUD_SQL_CONNECTION}"

if ! gcloud secrets describe "${DATABASE_URL_SECRET}" >/dev/null 2>&1; then
  gcloud secrets create "${DATABASE_URL_SECRET}" --replication-policy automatic
fi
printf '%s' "${DATABASE_URL}" | gcloud secrets versions add "${DATABASE_URL_SECRET}" --data-file=- >/dev/null

CLOUD_BUILD_SERVICE_ACCOUNT="${CLOUD_BUILD_SERVICE_ACCOUNT:-$(gcloud builds get-default-service-account --project "${GCP_PROJECT_ID}")}"
gcloud artifacts repositories add-iam-policy-binding "${AR_REPOSITORY}" \
  --location "${GCP_REGION}" \
  --member "serviceAccount:${CLOUD_BUILD_SERVICE_ACCOUNT}" \
  --role roles/artifactregistry.writer \
  --quiet >/dev/null
gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member "serviceAccount:${CLOUD_BUILD_SERVICE_ACCOUNT}" \
  --role roles/run.admin \
  --quiet >/dev/null
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SERVICE_ACCOUNT}" \
  --member "serviceAccount:${CLOUD_BUILD_SERVICE_ACCOUNT}" \
  --role roles/iam.serviceAccountUser \
  --quiet >/dev/null

echo "Foundation created. Cloud SQL connection: ${CLOUD_SQL_CONNECTION}"
echo "No application was deployed. Submit cloudbuild.yaml after configuring Firebase Authentication and the initial admin UID."
echo "Use substitutions: _REGION=${GCP_REGION},_AR_REPOSITORY=${AR_REPOSITORY},_CLOUD_SQL_CONNECTION=${CLOUD_SQL_CONNECTION},_RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SERVICE_ACCOUNT},_DATABASE_URL_SECRET=${DATABASE_URL_SECRET},_FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID},_FIREBASE_WEB_API_KEY=${FIREBASE_WEB_API_KEY},_FIREBASE_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN}"
