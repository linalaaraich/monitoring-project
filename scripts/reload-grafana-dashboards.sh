#!/usr/bin/env bash
# Hot-reload Grafana provisioned dashboards after editing a JSON file in
# roles/grafana/files/dashboards/. Copies the file to the monitoring VM
# and triggers Grafana's reload API — no pod restart needed.
#
# Usage:  ./scripts/reload-grafana-dashboards.sh [dashboard-name]
#         (omit the name to sync all dashboards)

set -euo pipefail

MONITORING_HOST="${MONITORING_HOST:-deploy@52.202.21.192}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/ansible_key}"
DASH_DIR="$(cd "$(dirname "$0")/.."; pwd)/roles/grafana/files/dashboards"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"

if [[ $# -ge 1 ]]; then
  FILES=("$DASH_DIR/$1.json")
else
  FILES=("$DASH_DIR"/*.json)
fi

for src in "${FILES[@]}"; do
  base="$(basename "$src")"
  echo "[sync] $base"
  scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$src" "$MONITORING_HOST:/tmp/$base"
  ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$MONITORING_HOST" \
    "sudo cp /tmp/$base /var/lib/grafana/dashboards/$base && sudo chown 472:472 /var/lib/grafana/dashboards/$base && sudo chmod 644 /var/lib/grafana/dashboards/$base"
done

echo "[reload] triggering Grafana dashboard provisioner reload"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$MONITORING_HOST" \
  "curl -s -u $GRAFANA_USER:$GRAFANA_PASSWORD -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload"
echo
echo "[done]"
