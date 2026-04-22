# scripts/

Automation scripts for the CIRES observability platform. All are
idempotent and version-controlled; the goal is that from a fresh
checkout of this repo you can reproduce any ad-hoc operation that was
originally done by hand.

## Prerequisites

- `~/.ssh/ansible_key` for SSH to the k3s and monitoring VMs
- Local clone of `monitoring-triage-service` alongside this repo
- AWS credentials for account `735115318342` (CIRES infra)

## Scripts

### `redeploy-triage.sh`

Rebuild the triage service image from a local clone and roll the
deployment to pick it up.

```bash
# Default: uses ../monitoring-triage-service, tag = YYYY-MM-DDb
./scripts/redeploy-triage.sh

# Override repo path or tag
IMAGE_TAG=2026-04-22c ./scripts/redeploy-triage.sh
TRIAGE_REPO=/path/to/monitoring-triage-service ./scripts/redeploy-triage.sh
```

What it does, in order:

1. Pre-checks `triage_queue_depth == 0` on the current pod (aborts if
   an alert is in flight; pass `REDEPLOY_TRIAGE_FORCE=1` to override).
2. Tars the triage source, scp's to the k3s node.
3. `docker build` on the node, `docker save`, `k3s ctr images import`.
4. Tars + scp's the Helm chart.
5. `helm upgrade ai-stack --reuse-values --set imageTag=<TAG>`. Never
   `--reset-values` (that wipes user values like `monitoring.host` and
   `smtp.*`, per the 2026-04-22 incident).
6. `kubectl rollout status` on `ai-stack-triage`.

### `reload-grafana-dashboards.sh`

Push changed dashboard JSON to the monitoring VM and trigger Grafana's
provisioning reload — no pod restart needed.

```bash
# All dashboards
./scripts/reload-grafana-dashboards.sh

# Just one
./scripts/reload-grafana-dashboards.sh unified-overview
```

### `hourly-demo-test.sh`

Runs on the k3s VM (not locally) once per hour via cron. Each invocation:

1. Triggers 200 mixed GET/POST requests through Kong (creates traces + metrics).
2. Sends 5 malformed-JSON POSTs (induces 400s + Drain3 anomaly).
3. Fires a synthetic Grafana webhook at `ai-stack-triage:/webhook/grafana`
   with `alert_name=HourlyDemoTest_<hour>` and a 2-minute-back `startsAt`.
4. Sleeps 30s then snapshots the latest `/decisions` entry to
   `/var/log/cires-demo-tests.log`.

The LLM itself finishes 3–15 min after step 3 on CPU. Expect to find
the real verdict in the log tail roughly 10–20 min after each cron tick.

### `install-hourly-cron.sh`

One-shot installer. Idempotent — safe to re-run.

```bash
./scripts/install-hourly-cron.sh
```

Copies `hourly-demo-test.sh` and `../load-test.sh` to `/opt/cires-demo/`
on the k3s node and registers a crontab entry:

```
15 * * * * /bin/bash /opt/cires-demo/hourly-demo-test.sh >> /var/log/cires-demo-tests.log 2>&1
```

To remove: `ssh <k3s> 'crontab -l | grep -v cires-demo | crontab -'`
