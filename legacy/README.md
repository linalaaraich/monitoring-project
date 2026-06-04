# legacy/ — retired artifacts (DO NOT RUN)

These files are the old **docker-compose-on-a-VM** deployment path and the old
inventories that targeted estates which no longer exist. They were superseded by
the **k3s / Kubernetes** path (Sprint 2 extension) and are kept here for
historical reference and on-prem fallback only.

**Do not run any of these against the live estate.** They are not imported by
`playbooks/site.yml` and they reference host groups / hosts that the current
inventories do not define.

| File | Why retired |
|------|-------------|
| `application.yml` | App (spring-boot) now runs in k3s via Helm (`charts/spring-boot`). Targets the `application` host group, which no longer exists. |
| `network.yml` | Kong now runs in k3s via the `kong/kong` Helm release (`charts/kong`). Targets the `network` host group, which no longer exists. |
| `ai.yml` | The GPU/AI triage tier is now codified by `roles/triage_stack` via `playbooks/gpu-host.yml` / `playbooks/gpu.yml`. Targets the `ai` host group, which no longer exists. |
| `production.yml` | Old inventory pinning long-dead AWS EIPs (52.x) and the legacy three-VM layout. Replaced by `inventory/newacct.yml` (live) and `inventory/example.yml` (BYO template). |
| `tailnet.yml` | Old-account Tailscale MagicDNS inventory; the hosts it named were torn down 2026-06-02. Replaced by `inventory/newacct.yml`. |

The live deployment path is:
`playbooks/monitoring.yml` → `playbooks/k3s.yml` → `playbooks/k8s-manifests.yml`
(see `playbooks/site.yml`), with the GPU tier deployed separately via
`playbooks/gpu-host.yml`.

For a bring-your-own-infrastructure deployment, start from
`inventory/example.yml`.
