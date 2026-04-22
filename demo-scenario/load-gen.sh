#!/usr/bin/env bash
# Continuous load generator against the Spring Boot employees API through Kong.
# Keep running during the demo to produce metrics/logs/traces.
#
# Env: KONG_URL  (e.g. http://<k3s-ip>:30080)
# Flags:
#   -r RPS        target requests/sec (default 5)
#   -c CONCURRENT in-flight requests (default 4)

set -euo pipefail

: "${KONG_URL:?set KONG_URL, e.g. export KONG_URL=http://<k3s-ip>:30080}"
RPS=5
CONCURRENT=4
while getopts "r:c:" opt; do
  case "$opt" in
    r) RPS="$OPTARG" ;;
    c) CONCURRENT="$OPTARG" ;;
    *) echo "usage: $0 [-r rps] [-c concurrent]" >&2; exit 2 ;;
  esac
done

DEPARTMENTS=(Engineering Marketing Sales HR Finance DevOps Support QA)
FIRST=(Lina Yousra Omar Sara Karim Fatima Amine Nadia Hassan Leila Mehdi Amal Youssef Salma)
LAST=(Laaraich Benali Idrissi Moussaoui Tazi Alaoui Fassi Berrada Lahlou Chraibi Ziani Mansouri)

pick() { echo "${@:$((RANDOM % $# + 1)):1}"; }

sleep_between=$(awk "BEGIN { printf \"%.3f\", 1/$RPS }")
echo "Load gen → $KONG_URL at ~${RPS} RPS (c=${CONCURRENT}). Ctrl+C to stop."

issue_one() {
  if (( RANDOM % 3 == 0 )); then
    first=$(pick "${FIRST[@]}"); last=$(pick "${LAST[@]}")
    dept=$(pick "${DEPARTMENTS[@]}")
    year=$((1980 + RANDOM % 21))
    payload=$(printf '{"firstName":"%s","lastName":"%s","department":"%s","gender":"Male","dateOfBirth":"%d-01-01"}' \
      "$first" "$last" "$dept" "$year")
    curl -sS -o /dev/null -w "%{http_code} POST\n" -X POST \
      -H "Content-Type: application/json" -d "$payload" \
      "$KONG_URL/api/employee" || true
  else
    curl -sS -o /dev/null -w "%{http_code} GET\n" "$KONG_URL/api/employee" || true
  fi
}

trap 'echo; echo "stopped"; exit 0' INT

in_flight=0
while true; do
  if (( in_flight < CONCURRENT )); then
    issue_one &
    in_flight=$((in_flight + 1))
  else
    wait -n || true
    in_flight=$((in_flight - 1))
  fi
  sleep "$sleep_between"
done
