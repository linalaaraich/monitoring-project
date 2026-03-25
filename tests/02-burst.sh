#!/usr/bin/env bash
# Burst: short high-concurrency spike — 500 requests, 80 concurrent
# Purpose: create a visible latency spike and throughput jump on dashboards
set -euo pipefail

KONG="http://192.168.127.15:8000"
TOTAL=500
BATCH=80

echo "=== Burst: ${TOTAL} requests, ${BATCH} concurrent ==="
start=$(date +%s)
for ((i=1; i<=TOTAL; i++)); do
    curl -s -o /dev/null "${KONG}/api/employee" &
    if (( i % BATCH == 0 )); then
        wait
        printf "\r  %d/%d" "$i" "$TOTAL"
    fi
done
wait
elapsed=$(( $(date +%s) - start ))
echo -e "\n=== Burst done in ${elapsed}s ==="
