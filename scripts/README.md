# scripts/

Automation scripts for the CIRES observability platform. All are
idempotent and version-controlled; the goal is that from a fresh
checkout of this repo you can reproduce any ad-hoc operation that
was originally done by hand.

## Prerequisites

- `~/.ssh/ansible_key` for SSH to the k3s and monitoring VMs
- Local clone of `monitoring-triage-service` alongside this repo
- AWS credentials for account `735115318342` (CIRES infra)

## Scripts

### `redeploy-triage.sh`

Rebuild the triage service image from a local clone and roll the
deployment to pick it up.

```bash
./scripts/redeploy-triage.sh                          # default tag = YYYY-MM-DDb
IMAGE_TAG=2026-04-22c ./scripts/redeploy-triage.sh    # explicit tag
TRIAGE_REPO=/path/to/clone ./scripts/redeploy-triage.sh
EXTRA_SET="--set ollama.model=llama3.1:8b" ./scripts/redeploy-triage.sh
```

Pre-checks `triage_queue_depth == 0` (override with `REDEPLOY_TRIAGE_FORCE=1`
if you know what you're doing). Re-applies the chart-default tunables
(`lokiLogLimit`, `jaegerTraceLimit`, `prometheusRangeMinutes`,
`ollamaRequestTimeout`, `pipelineTimeout`) via explicit `--set` so
bumps in `values.yaml` actually take effect on upgrade. User-supplied
values (`monitoring.host`, `smtp.*`) remain protected by `--reuse-values`.

### `reload-grafana-dashboards.sh`

Push changed dashboard JSON to the monitoring VM and trigger Grafana's
provisioning reload — no pod restart needed.

```bash
./scripts/reload-grafana-dashboards.sh                    # all dashboards
./scripts/reload-grafana-dashboards.sh unified-overview   # just one
```

### `hourly-demo-test.sh`

Runs **on the k3s VM** (not locally) on a systemd timer. Each firing:

1. 200 mixed GET/POST requests through Kong (creates traces + metrics).
2. 5 malformed-JSON POSTs (induces 400s + Drain3 anomaly).
3. Synthetic Grafana webhook at `ai-stack-triage:/webhook/grafana`.
4. 30-second wait, then snapshot latest `/decisions` entry.

Output appended to `/var/log/cires-demo-tests.log`. The LLM verdict for
each fire lands in the log 10-40 min after the synthetic webhook,
depending on bundle size and queue depth.

### `install-demo-test-timer.sh`

Installs `hourly-demo-test.sh` as a systemd timer on the k3s VM.
Replaces the older cron-based installer (removed 2026-04-22 because
cron can't express 100-min intervals cleanly).

```bash
./scripts/install-demo-test-timer.sh                  # every 100 min
INTERVAL_MINUTES=60 ./scripts/install-demo-test-timer.sh  # every 60 min
FIRST_FIRE_DELAY=5min ./scripts/install-demo-test-timer.sh  # first fire in 5 min
```

Idempotent — re-running updates the timer in place and cleans up any
prior cron entries. `Persistent=true` means a missed firing (e.g. VM
was down) fires once on recovery.

Teardown:

```bash
ssh <k3s> 'sudo systemctl disable --now cires-demo-test.timer \
  && sudo rm -f /etc/systemd/system/cires-demo-test.{service,timer} \
  && sudo systemctl daemon-reload'
```

Check schedule: `ssh <k3s> 'systemctl list-timers cires-demo-test.timer'`

### `sandbox-planner-prompt.sh`

Sprint 3 feasibility test — no pipeline changes. Exercises a
candidate Planner-phase prompt (two-pass RCA design, see
`monitoring-docs/sprint3-backlog.md` §2c) against the live Ollama pod
with a synthetic connection-pool-exhaustion alert. Validates whether
`llama3.2:3b` can produce the planner-schema JSON
(`{reasoning, can_decide_now, requests:[typed]}`) reliably, or whether
the design needs a larger model (Sprint 3 item §3).

```bash
./scripts/sandbox-planner-prompt.sh
ssh <k3s> 'tail -100 /var/log/cires-sandbox-planner.log'
```

One-shot. Fires one Ollama `/api/chat` request and logs the raw output
plus a PASS/PARTIAL/FAIL validation line.
