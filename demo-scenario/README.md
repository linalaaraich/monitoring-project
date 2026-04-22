# Demo scenario — alert → triage → email RCA

Scripts + artifacts to drive an end-to-end demo of the CIRES observability
platform on a single-node k3s deployment. Assumes Terraform + Ansible are
applied and the `ai-stack` Helm chart is installed.

## Prereqs

Set two env vars before running anything here:

```bash
export KONG_URL="http://<k3s-public-ip>:<kong-nodeport>"     # e.g. :30080
export KUBECONFIG="$HOME/.kube/k3s-demo.yaml"                 # from k3s node
```

Smoke-check connectivity:

```bash
curl -sf "$KONG_URL/api/employee" | head
kubectl get pods -A
```

## Walkthrough

1. **Warm the stack with traffic** (separate terminal, keep running):
   ```bash
   ./load-gen.sh
   ```
   Generates ~5 RPS against the Spring Boot API through Kong. Lets metrics,
   logs, and traces populate Prometheus, Loki, and Jaeger.

2. **Let it run for 5–10 minutes.** Open Grafana at
   `http://<monitoring-vm-ip>:3000`; confirm the "Unified Overview" dashboard
   shows traffic, latency, and zero error rate.

3. **Inject the failure:**
   ```bash
   ./inject-failure.sh backend-down
   ```
   Scales the Spring Boot deployment to zero replicas. Kong will start
   returning 5xx; the "backend 5xx rate > 5%" Grafana alert fires within
   1–2 minutes and POSTs to the triage service webhook.

4. **Watch the AI RCA pipeline.** In a third terminal:
   ```bash
   kubectl logs -n ai -l app.kubernetes.io/component=triage -f
   ```
   You'll see: dedup → MCP context fan-out (Prometheus/Loki/Jaeger) → Ollama
   decision → email send. Expect ~15–25 s end-to-end (CPU inference on
   llama3.2:3b).

5. **Check your inbox.** The escalation email includes the alert context,
   the LLM's root cause, and a Grafana dashboard link.

6. **Restore:**
   ```bash
   ./reset.sh
   ```
   Scales the backend back to 1 replica. Alert clears automatically.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `load-gen.sh` gets connection refused | Kong NodePort not exposed | `kubectl -n app get svc kong` and set `KONG_URL` to its NodePort |
| Alert doesn't fire after 2 min | Grafana alert rule not imported | Import `grafana/demo-alert-rule.json` via UI → Alerting → Alert rules |
| Triage logs show "model not found" | Ollama still pulling | First pull of llama3.2:3b takes 2–3 min on a cold node; wait and retry |
| Email never arrives | SMTP creds wrong / blocked | Check `kubectl -n ai get secret triage-smtp` and the triage pod env |
| Ollama response > 40 s | CPU saturated by load-gen | Lower `load-gen.sh` RPS to 2 or stop it before injecting failure |

## Files

- `load-gen.sh` — parameterized HTTP load generator (POST + GET, employees API)
- `inject-failure.sh` — controlled failure injection (backend-down | slow-query | pod-kill)
- `reset.sh` — restore healthy state
- `grafana/demo-alert-rule.json` — Grafana alert rule to import if the Ansible role didn't preload it
