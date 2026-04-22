#!/usr/bin/env bash
# Install/refresh the demo-test schedule on the k3s VM as a systemd timer
# (was cron at :15 hourly — replaced because cron can't express
# "every 100 min" cleanly). Idempotent — safe to re-run.
#
# Schedule: every 100 minutes, starting 5 min after install. Runs
# hourly-demo-test.sh and logs to /var/log/cires-demo-tests.log.
#
# Why systemd over cron here:
#   - 100-min intervals are trivial (OnUnitActiveSec=100min) but impossible
#     in 5-field cron without helper scripts.
#   - Systemd handles "the VM was down, run missed firing once on recovery"
#     via Persistent=true — useful if the k3s VM ever restarts.
#   - `systemctl list-timers` gives a clean "next firing" view you can
#     check without parsing crontab output.
#
# Teardown:
#   ssh <k3s> 'sudo systemctl disable --now cires-demo-test.timer \
#     && sudo rm -f /etc/systemd/system/cires-demo-test.{service,timer} \
#     && sudo systemctl daemon-reload'

set -euo pipefail

K3S_HOST="${K3S_HOST:-deploy@52.5.239.234}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/ansible_key}"
SCRIPT_DIR="$(cd "$(dirname "$0")"; pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.."; pwd)"
INTERVAL_MINUTES="${INTERVAL_MINUTES:-100}"
# How long to wait between `systemctl enable` and the FIRST firing. Set
# longer if the triage pipeline has in-flight alerts you want to drain
# before piling on a new one. systemd-time syntax ("5min", "1h", etc.)
FIRST_FIRE_DELAY="${FIRST_FIRE_DELAY:-5min}"

echo "[stage] copying scripts to $K3S_HOST:/opt/cires-demo/"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" \
  "sudo mkdir -p /opt/cires-demo && sudo chown -R deploy:deploy /opt/cires-demo"
scp -o StrictHostKeyChecking=no -i "$SSH_KEY" \
  "$SCRIPT_DIR/hourly-demo-test.sh" \
  "$REPO_ROOT/load-test.sh" \
  "$K3S_HOST:/opt/cires-demo/"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" \
  "chmod +x /opt/cires-demo/*.sh && sudo touch /var/log/cires-demo-tests.log && sudo chown deploy:deploy /var/log/cires-demo-tests.log"

echo "[cleanup] removing any prior crontab entry"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" bash -se <<'EOF'
  crontab -l 2>/dev/null | grep -v '/opt/cires-demo/hourly-demo-test.sh' | { crontab - 2>/dev/null || true; } || true
EOF

echo "[systemd] writing unit + timer for every ${INTERVAL_MINUTES}-min firing"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" bash -se <<EOF
  sudo tee /etc/systemd/system/cires-demo-test.service >/dev/null <<UNIT
[Unit]
Description=CIRES demo RCA dataset builder (load + synthetic webhook)
Documentation=https://github.com/linalaaraich/monitoring-project/blob/main/scripts/README.md
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=deploy
ExecStart=/bin/bash /opt/cires-demo/hourly-demo-test.sh
StandardOutput=append:/var/log/cires-demo-tests.log
StandardError=append:/var/log/cires-demo-tests.log
UNIT

  sudo tee /etc/systemd/system/cires-demo-test.timer >/dev/null <<TIMER
[Unit]
Description=Fire the CIRES demo RCA test every ${INTERVAL_MINUTES} minutes
Documentation=https://github.com/linalaaraich/monitoring-project/blob/main/scripts/README.md

[Timer]
# OnActiveSec (relative to enable time) controls the FIRST fire only.
# OnUnitActiveSec (relative to the last run) controls subsequent fires.
# OnBootSec would fire immediately on a long-running VM (boot was hours
# ago, so any OnBootSec in the past triggers right away) — don't use it.
OnActiveSec=${FIRST_FIRE_DELAY}
OnUnitActiveSec=${INTERVAL_MINUTES}min
# If the VM was down when a firing was due, run it once on recovery.
Persistent=true
AccuracySec=30s

[Install]
WantedBy=timers.target
TIMER

  sudo systemctl daemon-reload
  sudo systemctl enable --now cires-demo-test.timer
  echo ""
  echo "--- active timer status ---"
  systemctl list-timers cires-demo-test.timer --no-pager 2>&1 | head -5
EOF

echo "[done]"
echo "Next firing: check 'systemctl list-timers cires-demo-test.timer' on the k3s VM."
echo "Logs:       /var/log/cires-demo-tests.log"
echo "Manual fire: ssh $K3S_HOST 'sudo systemctl start cires-demo-test.service'"
