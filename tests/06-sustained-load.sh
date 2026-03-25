#!/usr/bin/env bash
# Sustained heavy load: high concurrency over 2 minutes
# Purpose: push latency up, fill up trace and log pipelines, stress DB connections
set -euo pipefail

KONG="http://192.168.127.15:8000"
TOTAL=2000
BATCH=100

FIRST=("Lina" "Omar" "Sara" "Karim" "Fatima" "Amine" "Nadia" "Hassan")
LAST=("Laaraich" "Benali" "Idrissi" "Moussaoui" "Tazi" "Alaoui")
DEPTS=("Engineering" "Sales" "HR" "DevOps" "QA")
GENDERS=("Male" "Female")

rand() { local a=("$@"); echo "${a[$((RANDOM % ${#a[@]}))]}"; }

echo "=== Sustained load: ${TOTAL} requests, ${BATCH} concurrent ==="
start=$(date +%s)

for ((i=1; i<=TOTAL; i++)); do
    case $((RANDOM % 4)) in
        0|1) curl -s -o /dev/null "${KONG}/api/employee" ;;
        2)   curl -s -o /dev/null "${KONG}/" ;;
        3)   name="$(rand "${FIRST[@]}") $(rand "${LAST[@]}")"
             curl -s -o /dev/null -X POST "${KONG}/api/employee" \
                 -H "Content-Type: application/json" \
                 -d "{\"name\":\"${name}\",\"department\":\"$(rand "${DEPTS[@]}")\",\"dob\":\"1990-05-15\",\"gender\":\"$(rand "${GENDERS[@]}")\"}" ;;
    esac &

    if (( i % BATCH == 0 )); then
        wait
        elapsed=$(( $(date +%s) - start ))
        rps=$(( i / (elapsed + 1) ))
        printf "\r  %d/%d  (~%d req/s, %ds elapsed)" "$i" "$TOTAL" "$rps" "$elapsed"
    fi
done
wait
elapsed=$(( $(date +%s) - start ))
echo -e "\n=== Sustained load done: ${TOTAL} req in ${elapsed}s (~$(( TOTAL / (elapsed+1) )) req/s) ==="
