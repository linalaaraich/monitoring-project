#!/usr/bin/env bash
# Install the hourly demo-test cron on the k3s VM. Idempotent —
# safe to re-run. Copies hourly-demo-test.sh + load-test.sh into
# /opt/cires-demo/ on the k3s node and registers the cron.
#
# Schedule: every hour at :15. Logs to /var/log/cires-demo-tests.log.
#
# To remove:  ssh <k3s> 'crontab -l | grep -v cires-demo | crontab -'

set -euo pipefail

K3S_HOST="${K3S_HOST:-deploy@52.5.239.234}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/ansible_key}"
SCRIPT_DIR="$(cd "$(dirname "$0")"; pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.."; pwd)"

echo "[stage] copying scripts to $K3S_HOST:/opt/cires-demo/"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" \
  "sudo mkdir -p /opt/cires-demo && sudo chown -R deploy:deploy /opt/cires-demo"
scp -o StrictHostKeyChecking=no -i "$SSH_KEY" \
  "$SCRIPT_DIR/hourly-demo-test.sh" \
  "$REPO_ROOT/load-test.sh" \
  "$K3S_HOST:/opt/cires-demo/"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" \
  "chmod +x /opt/cires-demo/*.sh && sudo touch /var/log/cires-demo-tests.log && sudo chown deploy:deploy /var/log/cires-demo-tests.log"

echo "[cron] registering hourly entry (at :15)"
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" bash -se <<'EOF'
  # Remove any prior cires-demo entries (idempotent reinstall)
  crontab -l 2>/dev/null | grep -v '/opt/cires-demo/hourly-demo-test.sh' > /tmp/cron.new || true
  echo '15 * * * * /bin/bash /opt/cires-demo/hourly-demo-test.sh >> /var/log/cires-demo-tests.log 2>&1' >> /tmp/cron.new
  crontab /tmp/cron.new
  rm -f /tmp/cron.new
  echo "--- installed crontab ---"
  crontab -l | grep cires-demo || true
EOF

echo "[done]"
echo "First run will fire at :15 of the next hour. To run immediately:"
echo "  ssh $K3S_HOST 'bash /opt/cires-demo/hourly-demo-test.sh'"
