# What Still Needs To Be Done

> Project: Observability Platform — CIRES Technologies (Tanger Med)
> Date: 2026-03-25
> Demo: 2026-03-26 (tomorrow — keep changes conservative)

---

## 1. Commit and Push Staged Improvements (Immediate)

These changes are already implemented in the working directory but not committed:

**Modified files:**
- `inventory/group_vars/all.yml` — Added OTel Collector version and port config
- `inventory/group_vars/application.yml` — Changed endpoint to Docker service name, removed promtail_port
- `inventory/group_vars/network.yml` — Removed promtail_port
- `playbooks/application.yml` — Replaced promtail role with otel-collector
- `playbooks/network.yml` — Replaced promtail role with otel-collector
- `playbooks/templates/application-compose.yml.j2` — Replaced Promtail service with OTel Collector
- `playbooks/templates/network-compose.yml.j2` — Replaced Promtail service with OTel Collector
- `roles/grafana/files/dashboards/unified-overview.json` — Updated Loki queries from `job` to `service.name`
- `roles/kong/templates/kong.yml.j2` — Changed OTel endpoint from IP to Docker service name
- `roles/otel-collector/templates/otel-collector-config.yaml.j2` — Added filelog receivers, Loki exporter, conditional routing

**Deleted files (Promtail role removed):**
- `roles/promtail/defaults/main.yml`
- `roles/promtail/handlers/main.yml`
- `roles/promtail/tasks/main.yml`
- `roles/promtail/templates/promtail-config.yml.j2`

**Action:** Stage all changes, commit, and push.

---

## 2. Integration Test Activation

- Integration test import is already active in `playbooks/site.yml` (line 12: `- import_playbook: integration.yml`)
- Test the integration playbook standalone:
  ```bash
  ansible-playbook playbooks/integration.yml --tags "connectivity,health,load,verification"
  ```
- Verify all health checks pass and observability data flows work:
  - Traces → Jaeger (check `react-springboot-app` and `kong-gateway` services)
  - Logs → Loki (check `service.name` labels appear)
  - Metrics → Prometheus (check all scrape targets are UP)

---

## 3. Verification Tasks for New Features

- **Test OTel Collector logs pipeline:** Verify Loki receives logs via the OTel Collector's Loki exporter (`http://loki:3100/loki/api/v1/push`)
- **Verify Loki receives OTel Collector logs:** The current setup uses the OTel Collector's native `loki` exporter (not OTLP). Confirm logs appear in Grafana Explore with `{service.name=~".+"}` queries
- **Test new alert rules:** Trigger medium CPU/memory usage (80%) to ensure Alertmanager notifications fire
- **Validate trace-log correlation:** Check Grafana Loki datasource uses `labelName: trace_id` correctly — clicking a trace_id in logs should navigate to Jaeger
- **Test Grafana dashboard re-provisioning:** Ensure removing `grafana.db` when dashboards change works correctly (the grafana role handles this)

---

## 4. Grafana Dashboard Updates and Config

- **unified-overview.json:** Already updated — queries now use `{service.name=~".+"}` instead of `{job=~".+"}` to match OTel Collector resource attributes
- **Verify other dashboards:** Check `tracing-overview.json` and `otel-collector-health.json` don't reference stale `job` labels where `service.name` is now used
- **Datasource config (`datasources.yml.j2`):** Already updated with `labelName: trace_id` instead of `matcherRegex` for trace-log correlation
- **Check Grafana provisioning:** After deploying, verify all 3 dashboards load correctly and Loki log panels show data

---

## 5. Potential Issues to Resolve

- **Loki OTLP endpoint compatibility:** We removed Promtail entirely and now use OTel Collector on all VMs. The OTel Collector uses its native `loki` exporter to push logs to Loki's `/loki/api/v1/push` endpoint. This is compatible with Loki's existing API — no OTLP receiver needed on Loki side. Verify this works end-to-end.
- **Label consistency:** OTel Collector adds `service.name` as a resource attribute. Grafana dashboard queries now use `service.name` instead of `job`. Make sure all queries are consistent.
- **Kong OTel endpoint:** Kong's OTel plugin now sends traces to `http://otel-collector:4318/v1/traces` (Docker service name). This requires Kong and OTel Collector to be on the same Docker network (they are — same compose file on network-vm).
- **Spring Boot OTel endpoint:** Spring Boot now sends traces to `http://otel-collector:4317` (Docker service name). Same network requirement applies (same compose file on application-vm).
- **Filelog receivers:** OTel Collector on app-vm reads `/var/log/app/*.log`, on network-vm reads `/var/log/kong/*.log`. Verify these paths exist and have correct permissions in the Docker volume mounts.

---

## 6. Documentation Updates

- **Update CLAUDE.md:** Move integration test from "Not Yet Done" to "Completed" section. Update Promtail references to OTel Collector throughout.
- **Update HTML webpage (`index.html`):**
  - Replace all Promtail references with OTel Collector log collection
  - Update architecture ASCII diagram (Promtail → OTel Collector on app/network VMs)
  - Update compose sections (application-vm and network-vm now have OTel Collector, not Promtail)
  - Update logs pipeline diagram and explanation
  - Update trace-log correlation section (OTel Collector filelog extracts trace_id, not Promtail)
  - Update sidebar nav (rename Promtail section to OTel Collector Log Collection)
  - Add integration testing section
  - Add future enhancements section
- **Update `architecture.html`:**
  - Replace Promtail service cards with OTel Collector on app/network VMs
  - Update data flows table (Promtail → OTel Collector for log shipping)
  - Update JSON schema (replace Promtail entries with OTel Collector)
  - Update pillar summary cards (Logs pillar: OTel Collector, not Promtail)
- **Add integration test documentation:** Detail how to run and interpret results

---

## 7. Future Enhancements (add to HTML webpage)

### Near-term
- **Credential hardening:** Replace weak defaults (`admin`/`123456789`) with Ansible Vault-encrypted secrets
- **Drain3 anomaly detector:** Automated log pattern clustering for anomaly detection
- **LLM triage service (:8090):** AI-powered incident triage with 4 MCP servers
- **Ollama (:11434):** Local LLM for cost-effective AI triage

### Medium-term
- **Tail-based trace sampling:** Add OTel Collector tail sampling processor to reduce storage while keeping interesting traces
- **Multi-environment support:** Extend Ansible inventory for staging/production environments
- **SSL/TLS everywhere:** Add TLS termination at Kong and inter-service encryption
- **Grafana alerting migration:** Move from Prometheus Alertmanager to Grafana-managed alerts for unified alert management
- **Log-based metrics:** Use Loki recording rules to generate metrics from log patterns

### Long-term
- **High availability:** Multi-node Prometheus (Thanos/Mimir), Loki clustering, Jaeger with Elasticsearch backend
- **GitOps deployment:** ArgoCD or Flux for automated config sync
- **Service mesh:** Istio/Linkerd for automatic mTLS and deeper traffic observability

---

## Priority Order

1. **Commit current changes** — Preserve work done (Promtail→OTel Collector migration)
2. **Test integration playbook** — Validate entire stack works end-to-end
3. **Verify OTel Collector logs pipeline** — Fix any Loki compatibility issues
4. **Update HTML documentation** — Reflect current architecture accurately
5. **Address future enhancements** — Start with credential hardening post-demo

---

## Summary

The project has a solid foundation with 16 Ansible roles (promtail deleted, replaced by distributed OTel Collector), three docker-compose templates, and a full observability stack covering metrics, logs, and traces. The major recent change is the migration from Promtail to OTel Collector for log collection, which consolidates the telemetry pipeline into a single agent (OTel Collector handles both traces and logs). The integration test playbook validates the entire stack works end-to-end. These remaining items will finalize documentation, verify the new pipeline, and prepare for the demo.
