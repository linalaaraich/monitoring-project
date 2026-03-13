#!/usr/bin/env bash
# Load test script: generates traffic through Kong and the Spring Boot API
# - 9000 requests to Kong proxy (192.168.127.15:8000)
# - Inserts test employees into the database via the API
# - Reads the employee list via /api/employee

set -euo pipefail

KONG="http://192.168.127.15:8000"
APP="http://192.168.127.30:80"
TOTAL=9000
BATCH=50        # parallel requests per batch
INSERTED=0
ERRORS=0

DEPARTMENTS=("Engineering" "Marketing" "Sales" "HR" "Finance" "DevOps" "Support" "QA")
GENDERS=("Male" "Female")
FIRST_NAMES=("Lina" "Yousra" "Omar" "Sara" "Karim" "Fatima" "Amine" "Nadia" "Hassan" "Leila"
             "Mehdi" "Amal" "Youssef" "Salma" "Zakaria" "Hind" "Rachid" "Imane" "Tariq" "Soukaina")
LAST_NAMES=("Laaraich" "Benali" "Idrissi" "Moussaoui" "Tazi" "Alaoui" "Fassi" "Berrada"
            "Lahlou" "Chraibi" "Ziani" "Mansouri" "Hajji" "Bouzid" "Kettani")

rand_element() {
    local arr=("$@")
    echo "${arr[$((RANDOM % ${#arr[@]}))]}"
}

rand_date() {
    # Random DOB between 1980 and 2000
    local year=$((1980 + RANDOM % 21))
    local month=$(printf "%02d" $((1 + RANDOM % 12)))
    local day=$(printf "%02d" $((1 + RANDOM % 28)))
    echo "${year}-${month}-${day}"
}

echo "=== Load Test: ${TOTAL} requests through Kong (${KONG}) ==="
echo "    Inserting employees & reading them back"
echo ""

start_time=$(date +%s)

for ((i = 1; i <= TOTAL; i++)); do
    first=$(rand_element "${FIRST_NAMES[@]}")
    last=$(rand_element "${LAST_NAMES[@]}")
    dept=$(rand_element "${DEPARTMENTS[@]}")
    gender=$(rand_element "${GENDERS[@]}")
    dob=$(rand_date)

    # Alternate between POST (insert) and GET (view) through Kong
    if (( i % 3 == 0 )); then
        # GET — view employees through Kong
        curl -s -o /dev/null -w "" "${KONG}/api/employee" &
    elif (( i % 3 == 1 )); then
        # POST — insert employee through Kong
        curl -s -o /dev/null -w "" \
            -X POST "${KONG}/api/employee" \
            -H "Content-Type: application/json" \
            -d "{\"name\":\"${first} ${last}\",\"department\":\"${dept}\",\"dob\":\"${dob}\",\"gender\":\"${gender}\"}" &
        INSERTED=$((INSERTED + 1))
    else
        # GET — view employees directly on app VM
        curl -s -o /dev/null -w "" "${APP}/api/employee" &
    fi

    # Throttle: wait for batch to complete
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
echo "  Total requests:  ${TOTAL}"
echo "  POSTs (inserts): ~${INSERTED}"
echo "  Time elapsed:    ${elapsed}s"
echo ""

# Final check: view all employees
echo "=== Fetching employee list from ${APP}/api/employee ==="
count=$(curl -s "${APP}/api/employee" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
echo "  Total employees in database: ${count}"
echo ""
echo "=== View the app at http://192.168.127.30:8080/view ==="
