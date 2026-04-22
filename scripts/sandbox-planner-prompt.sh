#!/usr/bin/env bash
# Sprint-3 feasibility sandbox — does llama3.2:3b produce a valid
# Planner-phase JSON on a realistic alert, without any wiring into the
# live pipeline?
#
# Runs on the k3s VM, calls Ollama directly with a synthetic but
# realistic alert context + a planner prompt, and saves both raw and
# parsed output for review.
#
# Usage (from control machine):
#   ./scripts/sandbox-planner-prompt.sh
#
# Output lands at:
#   /var/log/cires-sandbox-planner.log  (on the k3s VM)

set -euo pipefail

K3S_HOST="${K3S_HOST:-deploy@52.5.239.234}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/ansible_key}"

ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" bash -se <<'REMOTE'
set -euo pipefail

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG=/var/log/cires-sandbox-planner.log
sudo touch "$LOG"; sudo chown deploy:deploy "$LOG"

echo "=== SANDBOX RUN $TS ===" | tee -a "$LOG"

# --- Planner system prompt (candidate for Sprint 3) ---
SYSTEM='You are the PLANNER phase of a two-pass SRE RCA pipeline.

You are given an alert and a small initial evidence bundle. Your job is
NOT to write a verdict. Your job is to decide what additional evidence
would make the root cause unambiguous, then emit a JSON plan listing the
specific data to fetch.

You MUST respond with a single JSON object matching this schema exactly:

{
  "reasoning": "<brief — what the initial bundle already suggests>",
  "can_decide_now": true|false,
  "requests": [
    {"type":"traces_by_id", "trace_ids":["<32-hex>", ...]},
    {"type":"logs_by_pattern", "pattern":"<regex or substring>", "window_seconds":<int>},
    {"type":"metric_instant", "promql":"<promql query>", "at":"<ISO timestamp>"},
    {"type":"operation_list", "service":"<service>"}
  ]
}

Rules:
- If the initial bundle is already sufficient to write a verdict, set
  can_decide_now=true and leave requests=[].
- If you need more, list AT MOST 5 concrete requests. Each request MUST
  use one of the four types above — do not invent new types.
- Do not write the verdict itself. Another phase will do that with the
  expanded evidence.
- STRICT: respond with valid JSON only. No markdown, no prose, no
  preamble. Just the JSON object.'

# --- Realistic-looking alert context ---
USER='## Alert
- Name: BackendHigh5xxRate
- Service: spring-boot
- Severity: critical
- Started: 2026-04-22T15:45:00Z
- Summary: HTTP 5xx rate exceeded 5% for 2 minutes on Spring Boot via Kong
- Description: sum(rate(kong_http_requests_total{code=~"5.."}[1m])) > 0.05

## Initial bundle (compact sample, 3 items per pillar)

### Metrics (Prometheus, 10-min window)
- up{job=~".*spring-boot.*"}: 1
- kong_http_requests_total{code="500"}: last value 14.3 req/s (up from 0.1)
- hikaricp_connections_active: 9 of 10 (usually 2-3)

### Logs (Loki, Drain3-annotated, 5 lines)
[KNOWN] 2026-04-22 15:44:30 INFO  GET /api/employee 200 OK
[ANOMALY] 2026-04-22 15:45:02 ERROR [trace_id=a4b3c2d1e0f1234567890abcdef01234] Transaction rolled back; HikariPool-1 - Connection is not available
[ANOMALY] 2026-04-22 15:45:10 ERROR [trace_id=b5c4d3e2f1g2345678901bcdef012345] HikariPool-1 - Timeout failure stats
[KNOWN] 2026-04-22 15:45:15 INFO  GET /actuator/health 200 OK
[ANOMALY] 2026-04-22 15:45:22 ERROR [trace_id=c6d5e4f3g2h3456789012cdef0123456] JdbcSQLException: Connection pool exhausted

### Traces (Jaeger, 3 headers only)
- trace=d1e0f9a8b7c6... op="GET /api/employee" duration=45ms
- trace=e2f1a0b9c8d7... op="GET /actuator/health" duration=12ms
- trace=f3g2b1c0d9e8... op="POST /api/employee" duration=8500ms

### RCA history
This alert has fired 2 time(s) in the last 7 days. Last seen 2026-04-22T14:10:00Z.

Decide what additional evidence to fetch.'

PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({
    'model': 'llama3.2:3b',
    'messages': [
        {'role':'system','content':sys.argv[1]},
        {'role':'user','content':sys.argv[2]}
    ],
    'stream': False,
    'format': 'json',
    'options': {'temperature': 0.1}
}))
" "$SYSTEM" "$USER")

echo "[sandbox] firing single /api/chat to Ollama (no timeout; expect 5-20 min on CPU)" | tee -a "$LOG"
echo "[sandbox] prompt chars: $(echo -n "$SYSTEM$USER" | wc -c)" | tee -a "$LOG"
START=$(date -u +%s)

# Call Ollama inside a pod that can reach it (the triage service already can).
RESPONSE=$(sudo k3s kubectl -n ai exec deploy/ai-stack-triage -- \
  curl -sS --max-time 3600 -X POST http://ai-stack-ollama:11434/api/chat \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" 2>&1)

END=$(date -u +%s)
echo "[sandbox] completed in $((END - START))s" | tee -a "$LOG"

# Extract the content from Ollama's response
CONTENT=$(echo "$RESPONSE" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get('message', {}).get('content', '<NO_CONTENT>'))
except Exception as e:
    print(f'<PARSE_ERR: {e}>')
")

echo "--- RAW MODEL OUTPUT ---" | tee -a "$LOG"
echo "$CONTENT" | tee -a "$LOG"
echo "--- VALIDATION ---" | tee -a "$LOG"

python3 - <<VALIDATE | tee -a "$LOG"
import json, sys
text = '''$CONTENT'''

try:
    obj = json.loads(text)
except Exception as e:
    print(f"FAIL: not valid JSON — {e}")
    sys.exit(0)

required = {"reasoning", "can_decide_now", "requests"}
missing = required - obj.keys()
if missing:
    print(f"FAIL: missing required keys: {missing}")
    sys.exit(0)

if not isinstance(obj["requests"], list):
    print("FAIL: 'requests' is not a list")
    sys.exit(0)

valid_types = {"traces_by_id", "logs_by_pattern", "metric_instant", "operation_list"}
bad_types = [r.get("type") for r in obj["requests"] if r.get("type") not in valid_types]
if bad_types:
    print(f"PARTIAL: valid JSON + schema but contains unknown request types: {bad_types}")
else:
    print(f"PASS: valid JSON, valid schema, {len(obj['requests'])} well-typed requests")
    print(f"       reasoning: {obj.get('reasoning','')[:150]}")
    print(f"       can_decide_now: {obj.get('can_decide_now')}")
    for r in obj["requests"]:
        print(f"       - {r.get('type')}: {json.dumps({k:v for k,v in r.items() if k!='type'})[:120]}")
VALIDATE

echo "" | tee -a "$LOG"
echo "=== SANDBOX RUN DONE ===" | tee -a "$LOG"
REMOTE
