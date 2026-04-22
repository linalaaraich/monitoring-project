#!/usr/bin/env bash
# Restore the Spring Boot backend to a healthy state after any
# inject-failure.sh mode. Safe to run even if nothing is broken.

set -euo pipefail

NS="${APP_NAMESPACE:-app}"
DEPLOY="${BACKEND_DEPLOY:-spring-boot}"
REPLICAS="${BACKEND_REPLICAS:-1}"

echo "Scaling $NS/$DEPLOY to $REPLICAS replica(s)…"
kubectl -n "$NS" scale deploy "$DEPLOY" --replicas="$REPLICAS"

echo "Clearing SLOW_QUERY_MS if set…"
kubectl -n "$NS" set env deploy/"$DEPLOY" SLOW_QUERY_MS-

echo "Waiting for rollout…"
kubectl -n "$NS" rollout status deploy/"$DEPLOY" --timeout=120s
echo "Healthy. Grafana alert should clear within 1–2 min."
