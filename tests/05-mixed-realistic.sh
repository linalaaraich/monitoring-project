#!/usr/bin/env bash
# Mixed realistic: simulates real user behavior — reads, writes, errors, pauses
# Purpose: create the most natural-looking dashboard variation
set -euo pipefail

KONG="http://192.168.127.15:8000"
APP="http://192.168.127.30:80"

DEPARTMENTS=("Engineering" "Marketing" "Sales" "HR" "Finance" "DevOps")
FIRST=("Lina" "Omar" "Sara" "Karim" "Fatima" "Amine" "Nadia" "Hassan" "Leila" "Mehdi")
LAST=("Laaraich" "Benali" "Idrissi" "Moussaoui" "Tazi" "Alaoui" "Fassi")
GENDERS=("Male" "Female")

rand() { local a=("$@"); echo "${a[$((RANDOM % ${#a[@]}))]}"; }
rand_date() { printf "%d-%02d-%02d" $((1985+RANDOM%16)) $((1+RANDOM%12)) $((1+RANDOM%28)); }

echo "=== Mixed realistic traffic: 5 phases over ~3 minutes ==="

# Phase 1: calm browsing (30s)
echo "[Phase 1/5] Calm browsing — 40 req @ ~1.3/s"
for ((i=1; i<=40; i++)); do
    curl -s -o /dev/null "${KONG}/" &
    curl -s -o /dev/null "${KONG}/api/employee" &
    if (( i % 10 == 0 )); then wait; printf "\r  %d/40" "$i"; fi
    sleep 0.7
done
wait; echo ""

# Phase 2: data entry burst (20s)
echo "[Phase 2/5] Data entry burst — 60 POSTs"
for ((i=1; i<=60; i++)); do
    name="$(rand "${FIRST[@]}") $(rand "${LAST[@]}")"
    curl -s -o /dev/null -X POST "${KONG}/api/employee" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"${name}\",\"department\":\"$(rand "${DEPARTMENTS[@]}")\",\"dob\":\"$(rand_date)\",\"gender\":\"$(rand "${GENDERS[@]}")\"}" &
    if (( i % 15 == 0 )); then wait; printf "\r  %d/60" "$i"; fi
done
wait; echo ""

# Phase 3: quiet period (15s pause then trickle)
echo "[Phase 3/5] Quiet period — 15s pause then 10 slow requests"
sleep 15
for ((i=1; i<=10; i++)); do
    curl -s -o /dev/null "${KONG}/api/employee"
    sleep 1.5
done
echo "  done"

# Phase 4: error storm (20s)
echo "[Phase 4/5] Error storm — 100 bad requests"
BAD=("/api/nonexistent" "/null" "/api/employee/99999" "/missing" "/api/../etc" "/api/NOPE")
for ((i=1; i<=100; i++)); do
    curl -s -o /dev/null "${KONG}${BAD[$((RANDOM % ${#BAD[@]}))]}" &
    if (( i % 25 == 0 )); then wait; printf "\r  %d/100" "$i"; fi
done
wait; echo ""

# Phase 5: recovery + mixed traffic (30s)
echo "[Phase 5/5] Recovery — mixed GET/POST via Kong + direct"
for ((i=1; i<=80; i++)); do
    case $((RANDOM % 5)) in
        0) curl -s -o /dev/null "${KONG}/" ;;
        1) curl -s -o /dev/null "${KONG}/api/employee" ;;
        2) curl -s -o /dev/null "${APP}/api/employee" ;;
        3) name="$(rand "${FIRST[@]}") $(rand "${LAST[@]}")"
           curl -s -o /dev/null -X POST "${KONG}/api/employee" \
               -H "Content-Type: application/json" \
               -d "{\"name\":\"${name}\",\"department\":\"$(rand "${DEPARTMENTS[@]}")\",\"dob\":\"$(rand_date)\",\"gender\":\"$(rand "${GENDERS[@]}")\"}" ;;
        4) curl -s -o /dev/null "${KONG}/api/nonexistent" ;;
    esac &
    if (( i % 20 == 0 )); then wait; printf "\r  %d/80" "$i"; fi
    sleep 0.3
done
wait; echo ""

echo "=== Mixed realistic done ==="
