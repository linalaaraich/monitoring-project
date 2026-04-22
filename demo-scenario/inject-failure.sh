#!/usr/bin/env bash
# Controlled failure injection for the demo.
#
#   backend-down   — scale Spring Boot to 0 replicas (5xx alert)
#   pod-kill       — delete one Spring Boot pod (brief outage + recovery)
#   slow-query     — add latency env var to Spring Boot (p95 alert)
#
# Each mode triggers a distinct Grafana alert rule downstream.

set -euo pipefail

MODE="${1:-}"
NS="${APP_NAMESPACE:-app}"
DEPLOY="${BACKEND_DEPLOY:-spring-boot}"

case "$MODE" in
  backend-down)
    echo "Scaling $NS/$DEPLOY to 0 replicas…"
    kubectl -n "$NS" scale deploy "$DEPLOY" --replicas=0
    echo "Done. Kong will return 5xx on /api/*. Alert fires in 1–2 min."
    ;;
  pod-kill)
    pod=$(kubectl -n "$NS" get pod -l app="$DEPLOY" -o name | head -1)
    [[ -z "$pod" ]] && { echo "no $DEPLOY pod found"; exit 1; }
    echo "Deleting $pod…"
    kubectl -n "$NS" delete "$pod" --wait=false
    echo "Done. Short window of 5xx until the replacement pod is ready."
    ;;
  slow-query)
    echo "Injecting SLOW_QUERY_MS=800 into $NS/$DEPLOY…"
    kubectl -n "$NS" set env deploy/"$DEPLOY" SLOW_QUERY_MS=800
    echo "Done. p95 latency will climb; latency alert fires in 2–3 min."
    ;;
  *)
    echo "usage: $0 {backend-down|pod-kill|slow-query}" >&2
    echo "env:   APP_NAMESPACE=$NS  BACKEND_DEPLOY=$DEPLOY" >&2
    exit 2
    ;;
esac
