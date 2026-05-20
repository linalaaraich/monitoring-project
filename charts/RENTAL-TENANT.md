# Rental tenant — chart mirror

The car-rental tenant (Spring Boot + Angular + MySQL) deployed to the `rental` namespace on `observability-rca-k3s` lives in three helm charts here:

| Directory | Chart.yaml name | Helm release | Purpose |
|---|---|---|---|
| `rental-backend/` | `backend` | `rental-backend` | Spring Boot REST API (8080) |
| `rental-frontend/` | `frontend` | `rental-frontend` | Angular SPA |
| `rental-db/` | `database` | `rental-db` | MySQL 8 with PVC on `local-path` |

> **Why the directory name and `Chart.yaml: name:` differ.** The original Azure DevOps repo named the inner charts `backend` / `frontend` / `database`. The live helm releases on k3s use the `rental-` prefix to disambiguate from the platform's own `spring-boot` + `frontend` charts (same cluster, different namespace). Both forms are real and intentional — directory rename here is the platform-side fix for the 2026-05-20 audit's I-1 drift.

## Source of truth

These charts were mirrored 2026-05-20 from `/tmp/AZURE-PROJECT/helm/{backend,frontend,database}/` on `observability-rca-k3s`, which was unpacked there from the upstream Azure DevOps `cires-car-rental` repo (one-shot scp from `claude-controller` 2026-05-19).

The k3s-host copy at `/tmp/AZURE-PROJECT/` remains the deployment-time artifact (matches what `helm` actually rendered). This directory is the **platform source-of-truth for audit purposes only** — re-runs of the deploy script (`/root/CAR_RENTAL_DEPLOY.sh`) still reference `/tmp/AZURE-PROJECT/helm/`.

If you redeploy from these charts, the override yamls live at `/tmp/{db,backend,frontend}-override.yaml` on the k3s host (see SESSION_HANDOFF.md § car-rental).

## Why mirror them in?

`monitoring-triage-service/app/config.py:service_deployment_type` declares `backend`, `rental-backend`, `rental-frontend`, `rental-mysql` as `k8s` services. Per the daily static audit (§3), every `k8s` entry must have a corresponding Deployment / DaemonSet / StatefulSet manifest under `monitoring-project/manifests/` or a Helm chart under `monitoring-project/charts/`. Mirroring satisfies that gate.

## Observability wiring (already live)

Not in these charts (these are application charts only):
- OTel Java agent injection on `rental-backend` — patched in-place at deploy time via `/tmp/otel_patch.py` on the k3s host (mirrors `app/spring-boot` exactly: traces + logs OTLP to `otel-collector.observability:4317`).
- Kong route `/rental → rental-backend` — `monitoring-project/charts/kong/kong-config.yaml` (commit `6cfe7e5`).
- Alert-rule widening for `rental` namespace — `monitoring-project/roles/grafana/templates/alertrules.yml.j2` `PodHigh*` rules (commit `b6f5d9b`).
- Triage `service_deployment_type` entries — `monitoring-triage-service/app/config.py` (commit `8566596`).

## Tenant status

Per Lina's framing: *"doesn't deserve to be mentioned in the sprints, just do it quickly yourself."* The rental tenant is **not a platform deliverable** — it's a parallel workload that exercises the platform under multi-tenant load. Treat any drift here as a tenant-side concern, not a platform sprint item.
