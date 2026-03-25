#!/usr/bin/env bash
# Writes: POST new employees to stress the database write path
# Purpose: create DB write load, increase MySQL metrics, generate trace spans
set -euo pipefail

KONG="http://192.168.127.15:8000"
TOTAL=150
BATCH=20

DEPARTMENTS=("Engineering" "Marketing" "Sales" "HR" "Finance" "DevOps" "Support" "QA" "Security" "Data")
FIRST=("Lina" "Yousra" "Omar" "Sara" "Karim" "Fatima" "Amine" "Nadia" "Hassan" "Leila"
       "Mehdi" "Amal" "Youssef" "Salma" "Zakaria" "Hind" "Rachid" "Imane" "Tariq" "Soukaina")
LAST=("Laaraich" "Benali" "Idrissi" "Moussaoui" "Tazi" "Alaoui" "Fassi" "Berrada" "Lahlou" "Chraibi")
GENDERS=("Male" "Female")

rand() { local a=("$@"); echo "${a[$((RANDOM % ${#a[@]}))]}"; }
rand_date() { printf "%d-%02d-%02d" $((1980+RANDOM%21)) $((1+RANDOM%12)) $((1+RANDOM%28)); }

echo "=== Write test: ${TOTAL} POSTs to create employees ==="
ok=0; err=0
for ((i=1; i<=TOTAL; i++)); do
    name="$(rand "${FIRST[@]}") $(rand "${LAST[@]}")"
    dept=$(rand "${DEPARTMENTS[@]}")
    gender=$(rand "${GENDERS[@]}")
    dob=$(rand_date)

    curl -s -o /dev/null --connect-timeout 5 \
        -X POST "${KONG}/api/employee" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"${name}\",\"department\":\"${dept}\",\"dob\":\"${dob}\",\"gender\":\"${gender}\"}" &

    if (( i % BATCH == 0 )); then
        wait
        printf "\r  %d/%d" "$i" "$TOTAL"
    fi
done
wait
echo -e "\n=== Writes done: ${TOTAL} POSTs ==="
