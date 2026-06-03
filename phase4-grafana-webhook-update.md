# Phase 4 — Cut Grafana's webhook over to the API Gateway

**Status:** NOT YET EXECUTED. Run only after Phase 2/3 are green and Lina says go.

This step swaps Grafana's `triage-webhook` contact point from the adolin-wsl
laptop URL to the AWS API Gateway in `us-west-2`. After it, every Grafana alert
takes the path:

    Grafana → API Gateway → Lambda (warm-start: forward to GPU instance)
                                 (cold-start: enqueue in SQS, GPU drains)

## 1. File to edit

`inventory/group_vars/monitoring.yml` — the variable feeds
`roles/grafana/templates/contactpoints.yml.j2` (which is the actual Grafana
provisioning template, but it just substitutes `{{ triage_service_webhook_url }}`,
so no template edit is needed).

## 2. The exact line change

Current value (line 29 of `inventory/group_vars/monitoring.yml`):

```yaml
triage_service_webhook_url: "http://100.117.118.70:8090/webhook/grafana"
```

Change to (substitute the real `<api-id>` from
`terraform output -raw api_gateway_invoke_url` — today it resolves to
`l5anj15qi0`):

```yaml
triage_service_webhook_url: "https://l5anj15qi0.execute-api.us-west-2.amazonaws.com/webhook/grafana"
```

Also delete or comment-out the now-stale "as of 2026-04-23 the triage service
runs on Lina's laptop" comment block immediately above the variable; replace
it with a one-liner pointing at this file.

## 3. Apply the change

From `/root/monitoring-project`:

```bash
# Just the Grafana role — re-renders contactpoints.yml and reloads Grafana
# provisioning. Much faster than the full monitoring playbook.
ansible-playbook playbooks/monitoring.yml --tags grafana --limit monitoring

# If --tags grafana isn't wired up, fall back to the whole monitoring play:
# ansible-playbook playbooks/monitoring.yml --limit monitoring
```

(Inventory + SSH key are pre-configured in `ansible.cfg`; remote user is
`deploy` with passwordless sudo per the monitoring-project CLAUDE.md.)

## 4. Verify Grafana picked up the new URL

```bash
# (a) The rendered file on monitoring-vm shows the new URL
ansible monitoring -m shell -a "grep -m1 url /etc/grafana/provisioning/alerting/contactpoints.yml"
# expect: url: "https://l5anj15qi0.execute-api.us-west-2.amazonaws.com/webhook/grafana"

# (b) Grafana reloaded provisioning (look for "finished to provision alerting")
ansible monitoring -m shell -a "docker logs --since 2m grafana 2>&1 | grep -i 'provision\\|contactpoint' | tail -20"

# (c) Trigger a test alert from the Grafana UI:
#     Alerting → Contact points → triage-webhook → "Test"
#     Should return 2xx. Check the Lambda's CloudWatch log group
#     /aws/lambda/triage-gateway for the inbound event.

# (d) End-to-end: confirm the triage stack on the GPU host saw the test alert
ssh ubuntu@observability-gpu-uswest2 \
  'sudo docker logs --since 2m ai-triage-service 2>&1 | grep -i "webhook\\|SmokeTest\\|TestAlert" | tail -20'
```

## 5. Rollback (if something is wrong)

Revert the line in `inventory/group_vars/monitoring.yml` to the laptop URL and
re-run the same `ansible-playbook` command. Grafana picks up the change within
~30 s of provisioning reload.

## 6. After this lands

- Decommission the laptop triage stack (adolin-wsl) — keep the data tarball on
  the GPU host as the migration evidence.
- Update `monitoring-docs` to reflect the new alerting topology.
- Close out Phase 4 in `/root/GPU_MIGRATION_PLAN_2026-05-21.md`.
