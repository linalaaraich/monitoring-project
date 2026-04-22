#!/usr/bin/env bash
# Hourly demo-dataset builder: run a load burst, fire a synthetic Grafana
# webhook at the triage service, and log the outcome. Designed for cron on
# the k3s VM — see scripts/install-hourly-cron.sh for setup.
#
# Each run:
#   1. Runs load-test.sh TOTAL=200 through Kong (creates traces + metrics)
#   2. Injects a malformed-JSON POST burst (triggers Drain3 anomalies)
#   3. Fires a synthetic Grafana alertmanager webhook to the triage service
#   4. Logs summary + the RCA decision ID (once it lands)
#
# Output: appended to /var/log/cires-demo-tests.log

set -euo pipefail

LOG="${LOG:-/var/log/cires-demo-tests.log}"
KONG="${KONG:-http://localhost:30080}"
TRIAGE_NS="${TRIAGE_NS:-ai}"
TRIAGE_DEP="${TRIAGE_DEP:-deploy/ai-stack-triage}"
ALERT_NAME_PREFIX="${ALERT_NAME_PREFIX:-HourlyDemoTest}"
SCRIPT_DIR="$(cd "$(dirname "$0")"; pwd)"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ALERT_NAME="${ALERT_NAME_PREFIX}_$(date -u +%H)"

echo "=== $TS — $ALERT_NAME ===" | tee -a "$LOG"

# --- 1. Load burst (200 reqs, mixed GET/POST/metrics) ---
echo "[$TS] load burst start" | tee -a "$LOG"
if [[ -x "$SCRIPT_DIR/load-test.sh" ]]; then
  KONG="$KONG" TOTAL=200 BATCH=25 bash "$SCRIPT_DIR/load-test.sh" 2>&1 | tail -5 >> "$LOG" || true
else
  for i in $(seq 1 200); do
    curl -s -o /dev/null "${KONG}/api/employee" &
    (( i % 25 == 0 )) && wait
  done
  wait
fi

# --- 2. Induced anomaly: 5 malformed-JSON POSTs ---
echo "[$TS] malformed POST burst" >> "$LOG"
for _ in 1 2 3 4 5; do
  curl -s -o /dev/null -w "http=%{http_code}\n" \
    -X POST "${KONG}/api/employee" \
    -H "Content-Type: application/json" \
    -d '{invalid' >> "$LOG" || true
done

# --- 3. Synthetic Grafana webhook ---
# The webhook envelope matches Grafana Alerting (v9+) format. startsAt is
# set 2 minutes in the past so the triage pipeline's context window overlaps
# the induced traffic above.
START_AT="$(date -u -d '2 minutes ago' +%Y-%m-%dT%H:%M:%SZ)"
FP="hourly-demo-$(date -u +%s)"
TRIAGE_CLUSTER_IP="$(sudo k3s kubectl -n $TRIAGE_NS get svc ai-stack-triage -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)"
TRIAGE_URL="${TRIAGE_URL:-http://${TRIAGE_CLUSTER_IP}:8090}"

cat >/tmp/hourly-webhook.json <<JSON
{
  "receiver": "triage-webhook",
  "status": "firing",
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname": "$ALERT_NAME",
      "service": "spring-boot",
      "instance": "spring-boot",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Synthetic hourly demo alert",
      "description": "Induced 5 malformed JSON POSTs to /api/employee within the last 2 minutes. Expected: 400s, Drain3 anomaly, RCA verdict."
    },
    "startsAt": "$START_AT",
    "fingerprint": "$FP"
  }],
  "groupLabels": { "alertname": "$ALERT_NAME" },
  "commonLabels": { "severity": "warning", "service": "spring-boot" }
}
JSON

echo "[$TS] firing webhook at $TRIAGE_URL" >> "$LOG"
RESP=$(sudo k3s kubectl -n "$TRIAGE_NS" exec "$TRIAGE_DEP" -- \
  curl -s -o /dev/null -w '%{http_code}' -X POST "http://localhost:8090/webhook/grafana" \
  -H "Content-Type: application/json" -d "$(cat /tmp/hourly-webhook.json)" 2>&1 || echo "???")
echo "[$TS] webhook HTTP $RESP" >> "$LOG"
rm -f /tmp/hourly-webhook.json

# --- 4. Brief wait, then record latest decision (may still be in flight) ---
sleep 30
LATEST=$(sudo k3s kubectl -n "$TRIAGE_NS" exec "$TRIAGE_DEP" -- \
  curl -s "http://localhost:8090/decisions?limit=1" 2>&1 | head -c 400 || true)
echo "[$TS] latest decision snapshot: $LATEST" >> "$LOG"
echo "" >> "$LOG"
