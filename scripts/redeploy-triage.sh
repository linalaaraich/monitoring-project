#!/usr/bin/env bash
# Rebuild the triage service image from a local clone of monitoring-triage-service
# and roll the ai-stack deployment to pick it up.
#
# Required on the control machine:
#   - ~/.ssh/ansible_key
#   - monitoring-triage-service cloned alongside this repo
#
# Env overrides:
#   TRIAGE_REPO   path to local monitoring-triage-service clone  (default: ../monitoring-triage-service)
#   K3S_HOST      ssh target (default: deploy@52.5.239.234)
#   IMAGE_TAG     tag to build (default: today's date + "b", so 2026-04-23b)
#
# Safe to re-run: the helm upgrade uses --reuse-values so chart-level user
# values (monitoring.host, smtp.*) are preserved — never --reset-values.

set -euo pipefail

TRIAGE_REPO="${TRIAGE_REPO:-$(cd "$(dirname "$0")/../.."; pwd)/monitoring-triage-service}"
K3S_HOST="${K3S_HOST:-deploy@52.5.239.234}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y-%m-%d)b}"
CHART_DIR="$(cd "$(dirname "$0")/.."; pwd)/charts/ai-stack"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/ansible_key}"

if [[ ! -d "$TRIAGE_REPO/app" ]]; then
  echo "ERROR: TRIAGE_REPO=$TRIAGE_REPO does not look like monitoring-triage-service (no app/ dir)" >&2
  exit 1
fi

echo "=== Pre-check: nothing in flight ==="
QUEUE=$(ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" \
  "sudo k3s kubectl -n ai exec deploy/ai-stack-triage -- curl -s http://localhost:8090/metrics 2>/dev/null | grep -E '^triage_queue_depth ' | awk '{print \$2}' || echo missing")
echo "triage_queue_depth=$QUEUE"
if [[ "$QUEUE" != "0.0" && "$QUEUE" != "missing" ]]; then
  echo "ERROR: triage_queue_depth=$QUEUE — an alert is in flight. Abort to avoid killing an LLM call." >&2
  echo "Wait for it to complete or force with: REDEPLOY_TRIAGE_FORCE=1 $0" >&2
  [[ "${REDEPLOY_TRIAGE_FORCE:-0}" = "1" ]] || exit 2
fi

echo "=== Stage source ==="
TARBALL="/tmp/triage-service-src-$$.tgz"
tar --exclude=.git --exclude=__pycache__ --exclude=.pytest_cache \
  -C "$TRIAGE_REPO" -czf "$TARBALL" .
scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$TARBALL" "$K3S_HOST:/tmp/triage-src.tgz"
rm -f "$TARBALL"

echo "=== Build + import on k3s node (tag: $IMAGE_TAG) ==="
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" bash -se <<EOF
  set -euo pipefail
  sudo rm -rf /opt/build-triage
  sudo mkdir -p /opt/build-triage
  sudo tar -xzf /tmp/triage-src.tgz -C /opt/build-triage
  sudo chown -R deploy:deploy /opt/build-triage
  cd /opt/build-triage
  sudo docker build -t cires/triage-service:$IMAGE_TAG .
  sudo docker save cires/triage-service:$IMAGE_TAG -o /tmp/triage-$IMAGE_TAG.tar
  sudo k3s ctr images import /tmp/triage-$IMAGE_TAG.tar
  sudo rm -f /tmp/triage-$IMAGE_TAG.tar /tmp/triage-src.tgz
EOF

echo "=== Stage chart ==="
CHART_TARBALL="/tmp/ai-stack-chart-$$.tgz"
tar -C "$(dirname "$CHART_DIR")" -czf "$CHART_TARBALL" "$(basename "$CHART_DIR")"
scp -o StrictHostKeyChecking=no -i "$SSH_KEY" "$CHART_TARBALL" "$K3S_HOST:/tmp/ai-stack-chart.tgz"
rm -f "$CHART_TARBALL"

echo "=== helm upgrade (--reuse-values) ==="
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" "$K3S_HOST" bash -se <<EOF
  set -euo pipefail
  rm -rf /tmp/ai-stack-chart && mkdir -p /tmp/ai-stack-chart
  tar -xzf /tmp/ai-stack-chart.tgz -C /tmp/ai-stack-chart
  sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm upgrade ai-stack \
    /tmp/ai-stack-chart/ai-stack/ -n ai \
    --reuse-values \
    --set imageTag=$IMAGE_TAG
  sudo k3s kubectl -n ai rollout status deploy/ai-stack-triage --timeout=180s
  sudo k3s kubectl -n ai get pods -l app.kubernetes.io/component=triage-service
  sudo rm -f /tmp/ai-stack-chart.tgz
EOF

echo "=== Done — new triage pod is live ==="
