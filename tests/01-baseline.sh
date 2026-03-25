#!/usr/bin/env bash
# Baseline: steady low-rate traffic — ~200 requests over ~60s
# Purpose: establish a calm baseline on dashboards before stress tests
set -euo pipefail

KONG="http://192.168.127.15:8000"
TOTAL=200
DELAY=0.3 # seconds between requests

echo "=== Baseline: ${TOTAL} requests at ~3 req/s ==="
ok=0; err=0
for ((i=1; i<=TOTAL; i++)); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 "${KONG}/api/employee" 2>/dev/null || echo 000)
    if [[ "$code" == 2* ]]; then ok=$((ok+1)); else err=$((err+1)); fi
    if (( i % 20 == 0 )); then printf "\r  %d/%d  (ok=%d err=%d)" "$i" "$TOTAL" "$ok" "$err"; fi
    sleep "$DELAY"
done
echo -e "\n=== Baseline done: ok=$ok errors=$err ==="
