#!/usr/bin/env bash
# Errors: hit non-existent endpoints to generate 404s and bad requests
# Purpose: create visible error rate spikes in dashboards
set -euo pipefail

KONG="http://192.168.127.15:8000"
TOTAL=300
BATCH=30

BAD_PATHS=(
    "/api/nonexistent"
    "/api/employees/99999"
    "/api/employee/delete/-1"
    "/missing-page"
    "/api/../../../etc/passwd"
    "/api/employee?id=abc"
    "/favicon.ico"
    "/api/employee/0"
    "/null"
    "/api/EMPLOYEE"
)

echo "=== Error generation: ${TOTAL} requests to bad endpoints ==="
codes_4xx=0; codes_5xx=0; other=0
for ((i=1; i<=TOTAL; i++)); do
    path="${BAD_PATHS[$((RANDOM % ${#BAD_PATHS[@]}))]}"
    curl -s -o /dev/null "${KONG}${path}" &

    if (( i % BATCH == 0 )); then
        wait
        printf "\r  %d/%d" "$i" "$TOTAL"
    fi
done
wait
echo -e "\n=== Errors done: ${TOTAL} requests to bad endpoints ==="
