#!/usr/bin/env bash
# Load test: generates traffic through Kong NodePort -> Spring Boot -> RDS.
#
# Usage:
#   ./load-test.sh                       # default 9000 reqs, batch 50
#   TOTAL=500 BATCH=25 ./load-test.sh    # smaller run
#   KONG=http://localhost:30080 ./load-test.sh   # via SSH tunnel
#
# Environment overrides:
#   KONG      — Kong proxy URL (default http://<k3s EIP>:30080 from terraform output)
#   TOTAL     — total request count (default 9000)
#   BATCH     — concurrent batch size before wait (default 50)

set -euo pipefail

# Resolve Kong URL from terraform outputs if available, otherwise use override
if [ -z "${KONG:-}" ]; then
    if command -v terraform >/dev/null 2>&1 && [ -f ../provisioning-monitoring-infra/terraform.tfstate ]; then
        K3S_IP=$(cd ../provisioning-monitoring-infra && terraform output -raw k3s_public_ip 2>/dev/null || true)
        [ -n "$K3S_IP" ] && KONG="http://${K3S_IP}:30080"
    fi
fi
KONG="${KONG:-http://52.5.239.234:30080}"
TOTAL="${TOTAL:-9000}"
BATCH="${BATCH:-50}"

INSERTED=0
ERRORS=0

DEPARTMENTS=("Engineering" "Marketing" "Sales" "HR" "Finance" "DevOps" "Support" "QA")
GENDERS=("Male" "Female")
FIRST_NAMES=("Lina" "Yousra" "Omar" "Sara" "Karim" "Fatima" "Amine" "Nadia" "Hassan" "Leila"
             "Mehdi" "Amal" "Youssef" "Salma" "Zakaria" "Hind" "Rachid" "Imane" "Tariq" "Soukaina")
LAST_NAMES=("Laaraich" "Benali" "Idrissi" "Moussaoui" "Tazi" "Alaoui" "Fassi" "Berrada"
            "Lahlou" "Chraibi" "Ziani" "Mansouri" "Hajji" "Bouzid" "Kettani")

rand_element() { local arr=("$@"); echo "${arr[$((RANDOM % ${#arr[@]}))]}"; }
rand_date()    {
    local year=$((1980 + RANDOM % 21))
    local month=$(printf "%02d" $((1 + RANDOM % 12)))
    local day=$(printf "%02d" $((1 + RANDOM % 28)))
    echo "${year}-${month}-${day}"
}

echo "=== Load Test ==="
echo "  Kong:   $KONG"
echo "  Total:  $TOTAL requests"
echo "  Batch:  $BATCH concurrent"
echo ""

# Quick sanity check — fail fast if Kong is unreachable
if ! curl -fsS --max-time 5 "${KONG}/api/employee" >/dev/null 2>&1; then
    echo "ERROR: Kong at $KONG is not responding. Check:"
    echo "  1. kubectl get pods -n network  (kong-kong should be 1/1 Running)"
    echo "  2. kubectl get pods -n app      (spring-boot should be 1/1 Running)"
    echo "  3. Security group allows :30080 from your IP"
    exit 1
fi

start_time=$(date +%s)

for ((i = 1; i <= TOTAL; i++)); do
    first=$(rand_element "${FIRST_NAMES[@]}")
    last=$(rand_element "${LAST_NAMES[@]}")
    dept=$(rand_element "${DEPARTMENTS[@]}")
    gender=$(rand_element "${GENDERS[@]}")
    dob=$(rand_date)

    # 1/3 GET /api/employee (list), 1/3 POST (insert), 1/3 GET /actuator/prometheus (metrics hit)
    if (( i % 3 == 0 )); then
        curl -s -o /dev/null "${KONG}/api/employee" &
    elif (( i % 3 == 1 )); then
        curl -s -o /dev/null \
            -X POST "${KONG}/api/employee" \
            -H "Content-Type: application/json" \
            -d "{\"name\":\"${first} ${last}\",\"department\":\"${dept}\",\"dob\":\"${dob}\",\"gender\":\"${gender}\"}" &
        INSERTED=$((INSERTED + 1))
    else
        curl -s -o /dev/null "${KONG}/actuator/prometheus" &
    fi

    if (( i % BATCH == 0 )); then
        wait
        pct=$((i * 100 / TOTAL))
        printf "\r  Progress: %d/%d (%d%%)" "$i" "$TOTAL" "$pct"
    fi
done

wait
end_time=$(date +%s)
elapsed=$((end_time - start_time))

echo ""
echo ""
echo "=== Done ==="
echo "  Total requests:   ${TOTAL}"
echo "  POSTs (inserts):  ~${INSERTED}"
echo "  Time elapsed:     ${elapsed}s"
echo "  Effective rate:   $(( TOTAL / (elapsed > 0 ? elapsed : 1) )) req/s"
echo ""

count=$(curl -s --max-time 5 "${KONG}/api/employee" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
echo "  Total employees in database: ${count}"
echo ""
echo "Observe the effect:"
echo "  Grafana:  http://52.202.21.192:3000  (unified-overview dashboard)"
echo "  Jaeger:   http://52.202.21.192:16686 (see Kong -> Spring Boot traces)"
echo "  Loki:     via Grafana Explore, query {namespace=\"app\"}"
