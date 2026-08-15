#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${CLOUD_RUN_SERVICE:?Set CLOUD_RUN_SERVICE}"
: "${NOTIFICATION_CHANNEL:?Set NOTIFICATION_CHANNEL to a Monitoring channel resource name}"

GCP_REGION="${GCP_REGION:-asia-south1}"

if [[ "${CONFIRM_CREATE_MONITORING:-NO}" != "YES" ]]; then
  echo "Refusing to create alert policies. Set CONFIRM_CREATE_MONITORING=YES after reviewing thresholds."
  exit 2
fi

create_policy_if_missing() {
  local display_name="$1"
  shift
  if gcloud monitoring policies list \
    --project "${GCP_PROJECT_ID}" \
    --filter "displayName=${display_name}" \
    --format "value(name)" | grep -q .; then
    echo "Alert policy already exists: ${display_name}"
    return
  fi
  gcloud monitoring policies create \
    --project "${GCP_PROJECT_ID}" \
    --display-name "${display_name}" \
    --notification-channels "${NOTIFICATION_CHANNEL}" \
    "$@"
}

SERVICE_FILTER="resource.type=\"cloud_run_revision\" AND resource.label.service_name=\"${CLOUD_RUN_SERVICE}\" AND resource.label.location=\"${GCP_REGION}\""

create_policy_if_missing "Krishi Connect - any sustained 5xx responses" \
  --condition-display-name "5xx request count is above zero" \
  --condition-filter "${SERVICE_FILTER} AND metric.type=\"run.googleapis.com/request_count\" AND metric.label.response_code_class=\"5xx\"" \
  --duration 300s \
  --if "> 0" \
  --aggregation alignment-period=300s,per-series-aligner=ALIGN_RATE,cross-series-reducer=REDUCE_SUM

create_policy_if_missing "Krishi Connect - high memory utilization" \
  --condition-display-name "P99 memory utilization exceeds 85 percent" \
  --condition-filter "${SERVICE_FILTER} AND metric.type=\"run.googleapis.com/container/memory/utilizations\"" \
  --duration 300s \
  --if "> 0.85" \
  --aggregation alignment-period=60s,per-series-aligner=ALIGN_PERCENTILE_99,cross-series-reducer=REDUCE_MAX

create_policy_if_missing "Krishi Connect - high CPU utilization" \
  --condition-display-name "P99 CPU utilization exceeds 80 percent" \
  --condition-filter "${SERVICE_FILTER} AND metric.type=\"run.googleapis.com/container/cpu/utilizations\"" \
  --duration 300s \
  --if "> 0.80" \
  --aggregation alignment-period=60s,per-series-aligner=ALIGN_PERCENTILE_99,cross-series-reducer=REDUCE_MAX

echo "Created baseline Cloud Run alerts. Add an HTTPS uptime check for /readyz after the service URL is known."
