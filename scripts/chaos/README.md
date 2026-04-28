# Chaos test harness

End-to-end RCA quality measurement for the CIRES triage pipeline. Each test induces a real failure inside the production stack, polls `/decisions` for the resulting alert, captures the LLM's RCA, and scores it on four quality axes.

Built 2026-04-28 to operationalise the operator-flagged "make tests as real as possible" requirement — no synthetic webhook payloads, no mocked alerts. Real chaos against real pods.

## How to run

From the controller:

```bash
cd /root/monitoring-project
./scripts/chaos/runner.py                          # all tests, sequentially
./scripts/chaos/runner.py --tests target_down      # one test
./scripts/chaos/runner.py --tests target_down,drain3_anomaly   # subset
./scripts/chaos/runner.py --no-execute             # print plan, don't run
./scripts/chaos/runner.py --no-preflight           # skip alert-state check
```

Pre-flight verifies: triage `/health` returns healthy, monitoring stack is reachable, no unrelated alerts firing. Skip with `--no-preflight` if you're testing the harness itself.

## What each test does

| Short name | Alert it triggers | Action | Teardown |
|---|---|---|---|
| `target_down` | `TargetDown` | `kubectl scale deploy/spring-boot --replicas=0` | scale back to original count + wait for rollout |
| `high_memory` | `HighMemoryUsage` | lower spring-boot memory limit to 384Mi + rollout | restore limit + rollout restart |
| `high_cpu` | `HighCpuUsage` | spawn 4× `yes > /dev/null` inside spring-boot | rollout restart (kills burner processes) |
| `drain3_anomaly` | `Drain3AnomalyDetected` | write 50 lines of a never-before-seen error template to spring-boot stdout | nothing — log lines are immutable history |

Each test:
1. **setup()** — captures pre-state (original limits, replica counts, etc.).
2. **induce()** — applies the chaos action.
3. (runner polls `/decisions` for matching alertname + new timestamp, up to `timeout_s`)
4. **teardown()** — restores pre-state. **Always** runs, even if induce/poll failed (try/finally in the runner).

## Output

- **Raw JSON** at `scripts/chaos/reports/<utc-timestamp>.json` — all captured fields, scoring details, errors.
- **HTML report** at `monitoring-docs/chaos-report-<date>.html` — reviewable, links into the rest of the docs.

## Scoring (four axes, each 0/0.5/1.0; total = mean)

1. **Cause-first lede** — first sentence of the RCA names a component / process / link / mechanism. Implemented as inverted match against the validator's `_SURFACE_ONLY_LEDE_PATTERNS` + a hedge-tail check.
2. **Named cause** — the prose mentions a specific failing thing (connection pool, GC pause, NetworkPolicy, etc.) from a curated keyword list.
3. **Specific evidence** — the `evidence` list cites numbers, code-style strings, ms units, or quoted log lines (not just categories like "Prometheus metrics").
4. **State-changing action** — `suggested_actions[0]` is a remediation verb (kubectl rollout restart / helm rollback / etc.) per the same regex set the live validator uses.

Grade thresholds: A ≥ 0.85, B ≥ 0.65, C ≥ 0.40, F otherwise.

## Adding a new test

1. Subclass `ChaosTest` in a new file under `scripts/chaos/tests/<name>.py`.
2. Fill in `name`, `description`, `expected_alertname`, `timeout_s`.
3. Implement `setup()`, `induce()`, `teardown()` using primitives from `scripts/chaos/lib/ssh_actions.py`.
4. Register in `runner.py:REGISTRY`.

Test contract:
- `setup()` and `teardown()` MUST be idempotent — runner may retry on failure.
- `teardown()` is the truth — even if it duplicates work in `induce()`, it MUST leave the system as-found.
- `induce()` should NOT block longer than `timeout_s / 4` — the rest of the budget belongs to alert propagation + LLM reasoning.

## Adding a chaos action primitive

Edit `scripts/chaos/lib/ssh_actions.py`. Three host targets are supported:
- `K3S_HOST` (`observability-rca-k3s`, user `deploy`) — for kubectl / pod chaos. Joined the tailnet 2026-04-28.
- `LAPTOP_HOST` (`adolin-wsl`, user `lina`) — for triage-side chaos.
- `MONITORING_HOST` (`observability-rca-monitoring`, user `deploy`) — for Prometheus/Loki/Jaeger chaos.

All SSH uses `~/.ssh/ansible_key`.

## Safety

- Tests run sequentially with a 30s cool-down between them so the dedup window clears and the stack settles.
- Pre-flight aborts if the stack is unhealthy. Override with `--no-preflight` only when you understand the implications.
- Teardown failures are logged as CRITICAL but do not abort the run — the runner continues to the next test, then surfaces all teardown failures in the final report.
- Each test's `timeout_s` bounds the polling window. The runner does NOT time-bound `setup()` / `induce()` / `teardown()` themselves — those are expected to be fast.
- The chaos generates real escalation emails (if SMTP is configured) and real dashboard rows. They're not test data — they're real production observations of real injected failures, exactly as designed.

## Cadence

Phase 1 (current): ad-hoc by operator. After 2-3 successful runs the harness is trusted.

Phase 2: wire to `/schedule` (Claude Code routine) for weekly cron. The longitudinal chaos report becomes the quality signal — declining grade week-over-week is a regression to investigate.

Phase 3 (paired with US-5.7 corpus): each chaos test's expected RCA shape lands in `tests/corpus/` as a labeled example. F1 gates on chaos report regression in CI.

## Why this exists

The 2026-04-28 RCA quality audit (`monitoring-docs/rca-quality-audit-2026-04-28.html`) catalogued 5 distinct failure modes the production triage falls into. The morning's three-surface intervention (system prompt + exemplars + validator) addressed F-2 partially; the F-1 fix (Drain3 webhook evidence flow) addressed the dominant data-layer bug. But every fix so far was validated against either the test suite or one captured production case. Without live chaos:
- We can't measure whether F-2/F-3/F-4 remediations move the needle in production.
- Regressions are caught case-by-case as the operator notices them.
- The GPU migration to qwen2.5:14b (deferred multi-day effort) has no before/after baseline to evaluate against.

Live chaos closes those gaps.
