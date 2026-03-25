#!/usr/bin/env bash
# Run all test scripts in order with pauses between them
# This creates distinct phases visible in Grafana dashboards
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  Full Test Suite — $(date '+%H:%M:%S')"
echo "=========================================="
echo ""

for script in "$DIR"/0[1-6]-*.sh; do
    echo "--- Starting: $(basename "$script") at $(date '+%H:%M:%S') ---"
    bash "$script"
    echo ""
    echo "--- Pausing 20s before next test (visible gap in dashboards) ---"
    sleep 20
done

echo ""
echo "=========================================="
echo "  All tests complete — $(date '+%H:%M:%S')"
echo "  Open Grafana at http://192.168.127.10:3000"
echo "=========================================="
