# System Architecture: Observability Platform with AI-Powered Root Cause Analysis

**Project:** CIRES Technologies (Tanger Med) — Observability & AI RCA Platform
**Date:** 2026-03-30
**Status:** Finalized system design for Sprint 2 MVP (demo target: April 9, 2026)
**Audience:** Development team, NOC, Supervisors, Architecture reviewers

---

## 1. System Overview

This document defines the complete architecture of the CIRES observability platform with AI-powered Root Cause Analysis (RCA). The system monitors application infrastructure across metrics, logs, and distributed traces, then uses a three-layer AI pipeline to detect anomalies, triage alerts, and generate root cause analysis reports — ensuring developers only receive validated, actionable alerts.

### Design Principles

1. **No alert reaches a developer without AI evaluation.** The triage service is the sole gateway to human notification.
2. **All data stays internal.** No monitoring data or LLM inference leaves company-controlled infrastructure. Self-hosted LLM only.
3. **Zero application code changes for instrumentation.** Java services use OTel Java Agent (JVM flag). Other services use standard OTel SDKs. No plugins.
4. **Production-like architecture.** The AWS demo uses the same tier separation (S3 frontend, EC2 backend, managed RDS, dedicated monitoring and AI instances) that production will use.
5. **Infrastructure as Code.** Terraform provisions AWS resources. Ansible configures services. Everything is version-controlled and reproducible.

---

## 2. Infrastructure Layout

### 2.1 AWS Demo Environment (Terraform-Provisioned, us-east-1)

| Resource | AWS Type | Specs | Purpose |
|----------|----------|-------|---------|
| **Frontend** | S3 + CloudFront | Standard bucket + CDN | React static build (HTML/JS/CSS) |
| **Backend EC2** | t3.small | 2 vCPU, 2 GB RAM, 20 GB gp3 | Spring Boot API |
| **Database** | RDS db.t3.micro | 2 vCPU, 1 GB RAM, 20 GB gp3 | MySQL (managed, single-AZ) |
| **Network EC2** | t3.small | 2 vCPU, 2 GB RAM, 20 GB gp3 | Kong API Gateway |
| **Monitoring EC2** | t3.large | 2 vCPU, 8 GB RAM, 50 GB gp3 | Prometheus, Grafana, Loki, Jaeger, OTel Collector |
| **AI/LLM EC2** | g4dn.xlarge | 4 vCPU, 16 GB RAM + T4 GPU (16 GB VRAM), 50 GB gp3 | Ollama, Triage Service, MCP Servers, Drain3 |

### 2.2 Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        VPC (us-east-1)                          │
│                                                                 │
│  ┌─────────────── Public Subnet ──────────────────────────┐     │
│  │  CloudFront ← S3 (React frontend)                     │     │
│  │  NAT Gateway (for outbound from private subnet)        │     │
│  │  Bastion / SSH access (restricted to CIRES IPs)        │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
│  ┌─────────────── Private Subnet ─────────────────────────┐     │
│  │                                                        │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │     │
│  │  │ Monitoring   │  │ Backend      │  │ Network      │ │     │
│  │  │ EC2          │  │ EC2          │  │ EC2          │ │     │
│  │  │              │  │              │  │              │ │     │
│  │  │ Prometheus   │  │ Spring Boot  │  │ Kong Gateway │ │     │
│  │  │ Grafana      │  │ OTel Agent   │  │ OTel Plugin  │ │     │
│  │  │ Loki         │  │ node_export. │  │ Prom Plugin  │ │     │
│  │  │ Jaeger       │  │ cAdvisor     │  │ node_export. │ │     │
│  │  │ OTel Collect.│  │              │  │ cAdvisor     │ │     │
│  │  └──────────────┘  └──────┬───────┘  └──────────────┘ │     │
│  │                           │                            │     │
│  │  ┌──────────────┐  ┌──────┴───────┐                    │     │
│  │  │ AI/LLM       │  │ RDS MySQL    │                    │     │
│  │  │ EC2 (GPU)    │  │ (managed)    │                    │     │
│  │  │              │  │              │                    │     │
│  │  │ Ollama       │  │ db.t3.micro  │                    │     │
│  │  │ Triage Svc   │  │ Single-AZ    │                    │     │
│  │  │ MCP Servers  │  │ Private only │                    │     │
│  │  │ Drain3       │  └──────────────┘                    │     │
│  │  └──────────────┘                                      │     │
│  └────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Security Groups

| Security Group | Inbound Rules | Purpose |
|---------------|---------------|---------|
| **sg-monitoring** | SSH (CIRES IPs), 9090/3000/3100/16686/4317/4318/8888 from private subnet | Prometheus, Grafana, Loki, Jaeger, OTel Collector |
| **sg-backend** | SSH (CIRES IPs), 80 from sg-network, 8080 from private subnet, 9100/8081 from sg-monitoring | Spring Boot API + exporters |
| **sg-network** | SSH (CIRES IPs), 8000/8001 from private subnet, 9100/8081 from sg-monitoring | Kong proxy + admin + exporters |
| **sg-ai** | SSH (CIRES IPs), 8090 from sg-monitoring (webhooks from Grafana), 11434 from private subnet (Ollama) | Triage service + LLM |
| **sg-rds** | 3306 from sg-backend only | MySQL — no public access, backend-only |

---

## 3. Observability Stack

### 3.1 Three Pillars

| Pillar | Collection | Transport | Storage | Query |
|--------|-----------|-----------|---------|-------|
| **Metrics** | Prometheus scrapes `/metrics` endpoints on all services | Direct HTTP pull | Prometheus TSDB (monitoring EC2, EBS) | PromQL via Grafana |
| **Logs** | OTel Collector filelog receiver reads container log files | OTel Collector → Loki HTTP API | Loki TSDB (monitoring EC2, EBS) | LogQL via Grafana |
| **Traces** | Kong OTel plugin (HTTP) + Spring Boot OTel Java Agent (gRPC) | → OTel Collector → Jaeger (OTLP gRPC) | Jaeger Badger store (monitoring EC2, EBS) | Jaeger UI via Grafana |

### 3.2 Metrics Scrape Targets

| Target | Endpoint | Metrics Exposed |
|--------|----------|----------------|
| Spring Boot (via Kong) | kong:8000/actuator/prometheus | JVM, HTTP requests, connection pool, custom app metrics |
| Kong | kong:8001/metrics | Request count, latency, bandwidth, upstream health |
| MySQL (via exporter) | mysql-exporter:9104/metrics | Queries/sec, connections, replication lag, buffer pool |
| node_exporter (all VMs) | :9100/metrics | CPU, RAM, disk, network, filesystem |
| cAdvisor (all VMs) | :8081/metrics | Container CPU, RAM, network, I/O per container |
| OTel Collector | :8888/metrics | Spans received/exported, dropped, queue size |

### 3.3 Trace Flow

```
Browser (future: OTel JS SDK)
  → Kong (OTel plugin, W3C traceparent injection)
    → Spring Boot (OTel Java Agent, auto-instruments HTTP + JDBC)
      → MySQL/RDS (JDBC spans — query text, duration, db name)

Kong ──OTLP/HTTP──→ OTel Collector (:4318)
Spring Boot ──OTLP/gRPC──→ OTel Collector (:4317)
OTel Collector ──OTLP/gRPC──→ Jaeger (:4327)
```

**Trace propagation:** W3C Trace Context (primary) + B3 multi-header (compatibility). Both Kong and the OTel Java Agent use the same propagation format, ensuring a single trace spans from the API gateway through the backend to database queries.

**Database tracing:** The OTel Java Agent auto-instruments the JDBC driver. Every SQL query from Spring Boot to MySQL/RDS appears as a child span with the full query text, execution time, database name, and connection details. No MySQL-side plugin is needed — tracing is captured at the caller (Spring Boot) side.

### 3.4 Log Flow

```
Spring Boot container logs ──→ OTel Collector filelog receiver (backend VM)
Kong container logs ──→ OTel Collector filelog receiver (network VM)
                              ↓
                    OTel Collector Loki exporter
                              ↓
                    Loki (:3100, monitoring VM)
```

Spring Boot logs include `trace_id` in the log output (injected by the OTel Java Agent). The OTel Collector filelog receiver extracts `trace_id` using a regex parser operator, enabling log-to-trace correlation in Grafana.

### 3.5 Dashboards

| Dashboard | Purpose | Key Panels |
|-----------|---------|------------|
| **Unified Overview** | Single pane of glass for all services | Service health, request rate, error rate, latency percentiles, resource usage |
| **Tracing Overview** | Distributed trace analysis | Trace search, span duration heatmap, error spans, service dependency map |
| **OTel Collector Health** | Monitor the telemetry pipeline itself | Spans received/exported, drop rate, queue depth, exporter errors |

---

## 4. AI RCA Pipeline — Three Layers

**Important:** The triage service (Layer 2) is the sole orchestrator and action-taker in this pipeline. It receives alerts, calls Ollama, and — after receiving the LLM's analysis — sends the escalation email with the RCA report via SMTP, or logs the dismiss. Ollama (Layer 3) only produces analysis and returns it to the triage service. It does not send emails, store history, or take any external action.

### 4.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  LAYER 1 — Detection (pattern-matching, not smart)              │
│                                                                 │
│  ┌────────────────────────┐  ┌────────────────────────────────┐ │
│  │ Grafana Alerting       │  │ Drain3 Anomaly Detection       │ │
│  │                        │  │                                │ │
│  │ Rule-based threshold   │  │ Unsupervised log template      │ │
│  │ alerts evaluated       │  │ mining. Continuously ingests   │ │
│  │ against Prometheus     │  │ logs from Loki. Fires webhook  │ │
│  │ and Loki data sources. │  │ when new/unknown log patterns  │ │
│  │                        │  │ appear or anomaly rate spikes. │ │
│  │ Single webhook contact │  │                                │ │
│  │ point → triage service │  │ Webhook → triage service       │ │
│  └───────────┬────────────┘  └───────────────┬────────────────┘ │
│              │                               │                  │
│              └──────────┬────────────────────┘                  │
│                         ▼                                       │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  LAYER 2 — Triage Service (FastAPI :8090, smart routing)        │
│                                                                 │
│  Receives webhooks from Grafana Alerting and Drain3.            │
│                                                                 │
│  Step 1: Deduplicate                                            │
│    - Is this the same alert firing repeatedly? Group it.        │
│    - Has this exact alert been evaluated in the last N minutes? │
│      Skip if already processed.                                 │
│                                                                 │
│  Step 2: Correlate                                              │
│    - Did Grafana and Drain3 both fire at the same time?         │
│      Likely the same incident — merge into one investigation.   │
│    - Check RCA history: has this pattern been seen before?       │
│                                                                 │
│  Step 3: Decision                                               │
│    - Noise (known benign pattern, duplicate) → suppress & log   │
│    - Worth investigating → call Layer 3 (LLM)                   │
│                                                                 │
│  Step 4: Post-LLM Action                                        │
│    - LLM says valid + provides RCA → email devs via SMTP        │
│    - LLM says invalid → log with LLM reasoning, suppress        │
│                                                                 │
│  Step 5: Record                                                 │
│    - Store every decision in RCA History (SQLite)               │
│    - Whether suppressed, escalated, or resolved — all logged    │
│    - History is queryable by the LLM via MCP for future context │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼ (only if Layer 2 decides investigation needed)
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  LAYER 3 — LLM Analysis (Ollama, self-hosted)                   │
│                                                                 │
│  Called by the triage service with the alert context.            │
│  The LLM autonomously gathers additional data through           │
│  MCP bridges — it decides what to query, not us.                │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    MCP Bridges                            │   │
│  │                                                          │   │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐  │   │
│  │  │Prometheus MCP │ │  Loki MCP     │ │ Jaeger MCP    │  │   │
│  │  │               │ │               │ │               │  │   │
│  │  │ Query metrics │ │ Search logs   │ │ Find traces   │  │   │
│  │  │ Check rates   │ │ Filter by svc │ │ Span analysis │  │   │
│  │  │ Get history   │ │ Log volume    │ │ Error spans   │  │   │
│  │  └───────────────┘ └───────────────┘ └───────────────┘  │   │
│  │                                                          │   │
│  │  ┌───────────────┐ ┌──────────────────────────────────┐  │   │
│  │  │ Drain3 MCP    │ │ RCA History MCP                  │  │   │
│  │  │               │ │                                  │  │   │
│  │  │ Cluster stats │ │ Past RCA decisions               │  │   │
│  │  │ Anomaly rates │ │ Recurring patterns               │  │   │
│  │  │ Known vs new  │ │ Previous verdicts                │  │   │
│  │  │ Baseline info │ │ "Seen this 3x this week"         │  │   │
│  │  └───────────────┘ └──────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  LLM Output:                                                    │
│    - Alert validity verdict (valid / invalid / inconclusive)    │
│    - Root cause analysis report (if valid)                      │
│    - Confidence level                                           │
│    - Suggested remediation steps                                │
│    - Supporting evidence (which metrics, logs, traces it used)  │
│                                                                 │
│  Returns to Layer 2 for action.                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Layer 1 — Detection (Detail)

#### Grafana Alerting

| Property | Detail |
|----------|--------|
| **Replaces** | Prometheus Alertmanager (removed from the stack) |
| **How it works** | Grafana evaluates alert rules directly against Prometheus and Loki data sources on a configurable schedule (e.g., every 60s). When a rule fires, it sends a webhook POST to the triage service. |
| **Alert rules** | Defined in Grafana via UI or YAML provisioning. Examples: high latency (p95 > 500ms for 5m), high error rate (5xx > 5% for 3m), service down (up == 0 for 2m), OTel Collector span drop rate > 1%. |
| **Contact point** | Single webhook: `http://<ai-vm>:8090/webhook/grafana`. No email, no Slack, no PagerDuty. The triage service is the only recipient. |
| **Grouping** | Grafana groups related alerts (e.g., same service, same time window) before firing the webhook, reducing noise for the triage service. |

#### Drain3 Anomaly Detection

| Property | Detail |
|----------|--------|
| **What it is** | Unsupervised log template mining algorithm (by IBM Research). Parses log lines into structural templates using an online streaming algorithm. |
| **How it runs** | A background Python process on the AI/LLM VM continuously ingests logs from Loki (polling the Loki API at regular intervals). Each log line is fed through Drain3. |
| **What triggers a webhook** | When Drain3 encounters a log pattern it has never seen before (new template), or when the anomaly rate (ratio of unmatched logs to total logs) exceeds a configurable threshold, it fires a webhook to the triage service. |
| **Webhook** | `http://localhost:8090/webhook/drain3` with the anomalous log lines, matched/unmatched template info, and anomaly rate. |
| **Not a replacement for Grafana Alerting** | Drain3 catches things threshold alerts miss — novel log patterns, subtle structural changes in log output, unknown error messages. Grafana catches metric-based issues. They are complementary. |

#### Drain3 Baseline Management

The accuracy of Drain3 depends on its learned baseline — the set of "normal" log templates it has built from historical data. If the baseline becomes corrupted (e.g., it learns error patterns as normal because they persisted for days), its anomaly detection degrades. The system manages this through:

| Step | What | How | Automated? |
|------|------|-----|-----------|
| **1. Initial seeding** | Feed Drain3 a corpus of logs from a known healthy state | Collect logs during a clean load test with no errors. Feed them through Drain3 before it sees any real traffic. | Manual (first deploy only) |
| **2. Periodic snapshots** | Save Drain3's learned state to S3 at regular intervals | Serialize Drain3's internal tree to a file, upload to S3 with timestamp. Runs on a cron schedule (e.g., daily). | Yes — automated cron job |
| **3. Snapshot validation** | Tag snapshots as "known-good" when the system is confirmed healthy | After a period of confirmed healthy operation (no real incidents), tag the latest snapshot as a known-good baseline. | Semi-automated (trigger after confirmed healthy period) |
| **4. Drift detection** | Monitor Drain3's anomaly rate and template count over time | If the template count grows unexpectedly fast or the anomaly rate drops to near-zero (meaning it learned everything, including errors), flag potential drift. | Yes — metric exposed to Prometheus, alertable in Grafana |
| **5. Automated reset + re-seed** | Reset Drain3 and reload from the latest known-good snapshot | Scheduled periodic task (e.g., weekly) downloads the latest known-good snapshot from S3 and reinitializes Drain3. Can also be triggered manually. | Yes — automated scheduled task |

**S3 storage structure:**
```
s3://cires-observability-demo/drain3/
  ├── snapshots/
  │   ├── 2026-04-01T00:00:00Z.bin
  │   ├── 2026-04-02T00:00:00Z.bin
  │   └── ...
  └── baselines/
      └── known-good-2026-04-01.bin  (tagged as verified healthy)
```

#### Why Drain3 Exists Alongside Grafana Alerting

Grafana Alerting and Drain3 solve fundamentally different detection problems. Neither is redundant — they cover complementary blind spots.

**Grafana Alerting detects known failure modes.**
You write a rule: "fire when P95 latency exceeds 1 second for 2 minutes." This catches the failures you've already anticipated. But it can only alert on conditions you've explicitly defined. If a new failure mode appears that doesn't match any existing rule, Grafana stays silent.

**Drain3 detects unknown failure modes.**
It learns what "normal" log output looks like by building a template library from historical logs. When a log line appears that doesn't match any known template, Drain3 flags it as anomalous. No rules needed — it catches what you didn't think to look for.

| Scenario | Grafana Alerting | Drain3 |
|----------|-----------------|--------|
| P95 latency exceeds 1s | Fires (threshold rule exists) | Silent (not a log anomaly) |
| New `NullPointerException` in Spring Boot after deploy | Silent (no rule for this specific exception) | **Flags immediately** (new template never seen before) |
| Database connection pool slowly leaking | Fires late (only after latency/error thresholds breach) | **Flags early** ("Connection pool exhausted" is a new log pattern appearing before metrics react) |
| Known benign warning log repeating | Silent (no metric impact) | Silent (known template, high match count) |
| Sudden spike of `WARN: SSL handshake timeout` messages | Silent (no alert rule for this message) | **Flags** (new template or rate spike of a rare template) |
| Service crashes and stops logging entirely | Fires (`up == 0` rule) | Silent (no logs to analyze) |
| OTel Collector dropping spans | Fires (span drop rate rule) | Silent (metric-based issue) |

**Key insight:** Grafana Alerting is **reactive** — it fires after a predefined threshold is crossed, meaning the problem is already measurable. Drain3 is **proactive** — it detects the _cause_ (novel log patterns) before the _symptom_ (metric threshold breach) manifests.

**What Drain3 adds to the LLM investigation:**

Without Drain3, the LLM receives 50 raw log lines and must figure out which ones are relevant. With Drain3, every line is pre-annotated:

```
[KNOWN]  INFO  2026-04-05T10:30:01 Heartbeat check passed
[KNOWN]  INFO  2026-04-05T10:30:02 Request completed in 145ms
[ANOMALY] ERROR 2026-04-05T10:30:03 Connection pool exhausted — no available connections after 30s timeout
[ANOMALY] ERROR 2026-04-05T10:30:03 Failed to execute query: org.hibernate.exception.JDBCConnectionException
[KNOWN]  INFO  2026-04-05T10:30:04 Heartbeat check passed
```

The LLM immediately knows to focus on lines 3-4. The anomaly summary ("2 of 5 lines anomalous, 2 new patterns detected") gives it a quantitative signal before it even reads the logs. This reduces LLM inference time and improves RCA accuracy because the LLM isn't wasting tokens on routine log noise.

**In summary:** Grafana Alerting and Drain3 form a two-pronged detection layer. Grafana watches metrics with rules you define. Drain3 watches logs for patterns you didn't anticipate. Together, they ensure Layer 2 (triage service) receives signals from both known and unknown failure modes.

### 4.3 Layer 2 — Triage Service (Detail)

| Property | Detail |
|----------|--------|
| **Technology** | FastAPI (Python), runs on port 8090 on the AI/LLM VM |
| **Container** | Standalone Docker container with Drain3 embedded as an in-process library |
| **Webhook endpoints** | `POST /webhook/grafana` — receives Grafana Alerting payloads |
| | `POST /webhook/drain3` — receives Drain3 anomaly notifications (internal, same host) |
| **Decision logic** | Rule-based triage (not ML). Deduplication by alert fingerprint + time window. Correlation by timestamp proximity and affected service. Noise suppression for known benign patterns. |
| **LLM invocation** | When an alert passes triage, the service calls Ollama's `/api/chat` endpoint with a structured prompt containing the alert details, and instructs the LLM to use MCP tools for data gathering. |
| **Email notification** | Uses Python `smtplib` with Gmail SMTP (same credentials previously used by Alertmanager). Sends only when: Layer 3 returns a "valid" verdict with an RCA report. |
| **RCA History** | SQLite database on the AI/LLM VM. Stores every decision: timestamp, alert source, alert details, triage decision, LLM verdict, RCA report (if any), action taken. |

#### Triage Decision Flow

```python
# Simplified logic — not actual code, but illustrates the decision flow

def handle_webhook(alert):
    # Step 1: Deduplicate
    if is_duplicate(alert, window=timedelta(minutes=10)):
        log_suppressed(alert, reason="duplicate")
        return

    # Step 2: Check RCA history
    past = query_rca_history(alert.fingerprint, days=7)
    if past and past.last_verdict == "invalid" and past.count > 3:
        log_suppressed(alert, reason="repeatedly invalid per LLM")
        return

    # Step 3: Correlate with other recent alerts
    related = find_related_alerts(alert, window=timedelta(minutes=5))
    incident = merge_into_incident(alert, related)

    # Step 4: Call LLM for investigation
    rca_result = call_llm(incident)

    # Step 5: Act on LLM result
    if rca_result.verdict == "valid":
        send_email_to_devs(incident, rca_result)
        store_rca_history(incident, rca_result, action="emailed")
    else:
        store_rca_history(incident, rca_result, action="suppressed")
        log_suppressed(alert, reason=rca_result.reasoning)
```

#### Email Format

When the triage service sends an email to developers, it includes:

| Field | Content |
|-------|---------|
| **Subject** | `[ALERT] {severity}: {alert_name} — {affected_service}` |
| **Severity** | Critical / Warning (determined by Grafana rule + LLM confidence) |
| **Summary** | One-paragraph description of what's happening |
| **Root Cause Analysis** | LLM-generated RCA report with supporting evidence |
| **Evidence** | Links to relevant Grafana dashboard panels, specific log queries, trace IDs |
| **Suggested Actions** | LLM-generated remediation steps |
| **Confidence** | LLM's confidence level in the RCA (high/medium/low) |
| **History** | "This alert has fired N times in the last 7 days. Previous RCA: ..." |

### 4.4 Layer 3 — LLM Analysis (Detail)

| Property | Detail |
|----------|--------|
| **Runtime** | Ollama running on the AI/LLM VM (port 11434) |
| **Model** | Llama 3 8B or Mistral 7B (quantized, fits in T4 16GB VRAM) |
| **Inference** | Entirely local. No data leaves the VM. No external API calls. |
| **Invocation** | The triage service calls Ollama's HTTP API with a structured prompt + MCP tool definitions. |
| **Autonomy** | The LLM decides what data to gather. It can query any MCP bridge multiple times, in any order. The triage service provides the tools; the LLM drives the investigation. |

#### MCP Bridge Specification

| MCP Server | Data Source | Port | Available Tools |
|------------|-----------|------|-----------------|
| **Prometheus MCP** | Prometheus HTTP API (monitoring VM :9090) | 8091 | `query_instant(promql)` — run a PromQL query at current time |
| | | | `query_range(promql, start, end, step)` — run a PromQL range query |
| | | | `get_alerts()` — list all currently firing Prometheus alerts |
| | | | `get_targets()` — list all scrape targets and their health |
| **Loki MCP** | Loki HTTP API (monitoring VM :3100) | 8092 | `query_logs(logql, start, end, limit)` — search logs |
| | | | `get_label_values(label)` — list values for a log label |
| | | | `get_log_volume(logql, start, end)` — log volume over time |
| **Jaeger MCP** | Jaeger HTTP API (monitoring VM :16686) | 8093 | `find_traces(service, operation, start, end, limit)` — search traces |
| | | | `get_trace(trace_id)` — get full trace detail |
| | | | `get_services()` — list all traced services |
| | | | `get_operations(service)` — list operations for a service |
| **Drain3 MCP** | Drain3 in-memory state (same process) | 8094 | `get_clusters()` — list all known log templates |
| | | | `get_anomaly_rate()` — current ratio of unknown to known logs |
| | | | `match_log(log_line)` — check if a log line matches a known template |
| | | | `get_baseline_info()` — last reset time, snapshot age, template count |
| **RCA History MCP** | Triage service SQLite DB | 8095 | `get_recent_rcas(hours)` — recent RCA decisions |
| | | | `search_rcas(alert_name, days)` — find past RCAs for an alert |
| | | | `get_rca_detail(rca_id)` — full detail of a past RCA |
| | | | `get_alert_frequency(alert_name, days)` — how often this alert fires |

All MCP servers are **read-only**. The LLM cannot modify any data source, cannot write to the RCA history, and cannot trigger actions. It can only gather information and produce analysis. The triage service (Layer 2) is the only component that takes actions (email, store history).

#### LLM Prompt Structure

The triage service sends the LLM a structured prompt containing:

```
System: You are an SRE assistant analyzing an infrastructure alert. Use the
available tools to gather data from Prometheus (metrics), Loki (logs), Jaeger
(traces), Drain3 (log anomaly patterns), and RCA History (past investigations).

Your task:
1. Determine if this alert represents a real issue or a false positive.
2. If real, identify the root cause by correlating metrics, logs, and traces.
3. Provide a confidence level (high/medium/low) for your analysis.
4. Suggest remediation steps.

Alert context:
- Alert name: {alert_name}
- Source: {grafana|drain3}
- Severity: {severity}
- Affected service: {service}
- Alert message: {message}
- Time: {timestamp}
- Related alerts in the last 5 minutes: {related_alerts}

Available tools: [Prometheus MCP, Loki MCP, Jaeger MCP, Drain3 MCP, RCA History MCP]
```

---

## 5. Data Flow Diagrams

### 5.1 Request Path (User Traffic)

```
User Browser
  → CloudFront (HTTPS, S3 origin for static React assets)
  → Kong API Gateway (:8000, network EC2)
    - Injects W3C traceparent header
    - Sends trace span to OTel Collector (:4318 HTTP)
    → Spring Boot API (:8080, backend EC2)
      - OTel Java Agent captures HTTP span + JDBC spans
      - Sends traces to OTel Collector (:4317 gRPC)
      → RDS MySQL (private subnet, :3306)
        - JDBC query captured as child span by OTel Java Agent
        - No MySQL-side instrumentation needed
```

### 5.2 Telemetry Path

```
Metrics:
  Prometheus (monitoring EC2) ──scrape──→ Spring Boot /actuator/prometheus (via Kong)
  Prometheus ──scrape──→ Kong :8001/metrics
  Prometheus ──scrape──→ MySQL Exporter :9104/metrics
  Prometheus ──scrape──→ node_exporter :9100/metrics (all VMs)
  Prometheus ──scrape──→ cAdvisor :8081/metrics (all VMs)
  Prometheus ──scrape──→ OTel Collector :8888/metrics

Logs:
  Spring Boot container logs → OTel Collector filelog receiver (backend EC2)
  Kong container logs → OTel Collector filelog receiver (network EC2)
  OTel Collector → Loki :3100 (monitoring EC2)

Traces:
  Kong → OTel Collector :4318 HTTP (monitoring EC2)
  Spring Boot OTel Agent → OTel Collector :4317 gRPC (monitoring EC2)
  OTel Collector → Jaeger :4327 gRPC (monitoring EC2, internal Docker network)
```

### 5.3 Alert + AI RCA Path

```
Grafana Alerting (monitoring EC2)
  evaluates rules against Prometheus + Loki
    → webhook POST to http://ai-vm:8090/webhook/grafana

Drain3 (AI/LLM EC2, background process)
  polls Loki for new logs
  detects unknown patterns
    → webhook POST to http://localhost:8090/webhook/drain3

Triage Service (AI/LLM EC2 :8090)
  receives webhooks from both sources
  deduplicates, correlates, checks history
    → if worth investigating: calls Ollama (localhost:11434)
      → Ollama uses MCP bridges to query Prometheus, Loki, Jaeger, Drain3, RCA History
      → Ollama returns verdict + RCA report
    → if valid alert: triage service sends email via SMTP (outbound)
    → stores decision in SQLite (RCA History)
```

---

## 6. What Changed from Sprint 1

| Component | Sprint 1 | Sprint 2 (Current) | Reason |
|-----------|----------|-------------------|--------|
| **Alert evaluation** | Prometheus alert rules + Alertmanager | Grafana Alerting | Grafana evaluates against both Prometheus and Loki. Unified alert management UI. No need for separate Alertmanager. |
| **Alert notification** | Alertmanager sends email directly to devs | Triage service sends email after AI evaluation | No alert reaches devs without AI validation. Reduces alert fatigue. |
| **Alertmanager** | Running on monitoring VM | **Removed** | Replaced by Grafana Alerting (evaluation) + Triage Service (notification). |
| **Promtail** | Running on app + network VMs | **Removed** | Replaced by OTel Collector filelog receiver. One agent per VM instead of two. |
| **Log shipping** | Promtail → Loki | OTel Collector filelog receiver → Loki | Unified agent handles traces, metrics, and logs. |
| **Frontend hosting** | Bundled in Spring Boot container | S3 + CloudFront | Production-like separation. Static files served by CDN. |
| **Database** | MySQL in docker-compose on app VM | RDS db.t3.micro (managed) | Production-like managed database. Separate from compute. |
| **Application VM** | Spring Boot + MySQL + React (all together) | Backend EC2: Spring Boot only | Clean tier separation. |
| **AI/LLM** | Not yet implemented | Ollama + Triage Service + MCP Servers + Drain3 on dedicated GPU EC2 | Core Sprint 2 deliverable. |
| **IaC** | Ansible only | Terraform (infra) + Ansible (config) | Terraform provisions AWS resources. Ansible configures services. |

---

## 7. Removed Components

### 7.1 Alertmanager — Why It's Gone

Alertmanager was previously responsible for:
1. Receiving alerts from Prometheus
2. Grouping, deduplicating, and silencing alerts
3. Routing alerts to email (Gmail SMTP)

In the new architecture:
- **Function 1** (receiving alerts): Handled by Grafana Alerting, which evaluates rules directly.
- **Function 2** (grouping/dedup): Handled by Grafana Alerting (grouping) + Triage Service (deduplication and correlation).
- **Function 3** (email routing): Handled by the Triage Service, but only after AI evaluation confirms the alert is valid.

The Alertmanager Ansible role, config, and container are removed from the monitoring VM's docker-compose.

### 7.2 Promtail — Why It's Gone

Promtail was previously responsible for shipping logs from application and network VMs to Loki. It has been replaced by the OTel Collector's filelog receiver, which:
- Is already deployed on all VMs for trace collection
- Eliminates the need for a second agent (Promtail) on each VM
- Supports the same trace_id extraction for log-trace correlation
- Is maintained by the same OpenTelemetry project as the rest of the telemetry stack

### 7.3 Prometheus Alert Rules — Migrated

Prometheus alert rules (`roles/prometheus/files/alert-rules.yml`) are migrated to Grafana Alerting rules. The same logic (PromQL expressions, thresholds, evaluation intervals) is preserved, but now managed in Grafana's UI or YAML provisioning. This allows alert rules to also evaluate against Loki (LogQL) data sources, which Prometheus alerting rules could not do.

---

## 8. AI/LLM VM Services Summary

All AI-related services run on the dedicated GPU EC2 instance (g4dn.xlarge):

| Service | Port | Technology | Purpose |
|---------|------|-----------|---------|
| **Triage Service** | 8090 | FastAPI (Python) | Central decision-making. Receives webhooks, coordinates triage, calls LLM, sends email. |
| **Ollama** | 11434 | Ollama (Go) | Local LLM inference (Llama 3 8B / Mistral 7B) |
| **Drain3** | — (in-process) | Python library | Log anomaly detection. Runs inside the triage service process. Background log ingestion loop. |
| **Prometheus MCP** | 8091 | FastAPI (Python) | MCP bridge to Prometheus API |
| **Loki MCP** | 8092 | FastAPI (Python) | MCP bridge to Loki API |
| **Jaeger MCP** | 8093 | FastAPI (Python) | MCP bridge to Jaeger API |
| **Drain3 MCP** | 8094 | FastAPI (Python) | MCP bridge to Drain3 in-memory state |
| **RCA History MCP** | 8095 | FastAPI (Python) | MCP bridge to triage service SQLite DB |

**Total services on AI/LLM VM: 8** (1 triage + 1 LLM runtime + 5 MCP servers + Drain3 embedded)

**Resource allocation:**
- Ollama: Uses GPU (T4 16 GB VRAM) + ~6-10 GB system RAM for model inference
- Triage Service + Drain3: ~500 MB RAM
- MCP Servers (5x): ~100 MB RAM each, ~500 MB total
- Headroom: ~5 GB system RAM remaining for OS, Docker, and buffers

---

## 9. RCA History Storage

### 9.1 Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | TEXT (UUID) | Unique RCA record ID |
| `timestamp` | DATETIME | When the alert was received |
| `alert_source` | TEXT | "grafana" or "drain3" |
| `alert_name` | TEXT | Alert rule name or Drain3 anomaly type |
| `alert_fingerprint` | TEXT | Hash for deduplication |
| `affected_service` | TEXT | Service name from alert labels |
| `severity` | TEXT | critical / warning / info |
| `triage_decision` | TEXT | "investigate" / "suppress_duplicate" / "suppress_known_benign" / "suppress_repeated_invalid" |
| `llm_verdict` | TEXT | "valid" / "invalid" / "inconclusive" / NULL (if not escalated to LLM) |
| `llm_confidence` | TEXT | "high" / "medium" / "low" / NULL |
| `rca_report` | TEXT | Full LLM-generated RCA report (if valid) |
| `llm_reasoning` | TEXT | LLM's explanation for its verdict |
| `action_taken` | TEXT | "emailed" / "suppressed" / "logged" |
| `related_alerts` | TEXT (JSON) | Array of related alert IDs that were correlated |
| `investigation_duration_ms` | INTEGER | Time taken for the full pipeline (triage + LLM) |

### 9.2 Retention

- SQLite file on the AI/LLM VM's EBS volume
- Retain all records for the demo sprint
- Production: consider migrating to PostgreSQL with a 90-day retention policy

### 9.3 LLM Access Pattern

When the LLM investigates a new alert, it can query RCA History via MCP to answer:
- "Has this alert name fired before? How many times in the last 7 days?"
- "What was the previous root cause for this alert?"
- "Was this alert previously marked valid or invalid?"
- "Are there recurring patterns — same alert, same time of day, same service?"

This gives the LLM **institutional memory** — each investigation is informed by all previous investigations. Over time, the system gets smarter at recognizing recurring issues and avoids repeating analysis it has already done.

---

## 10. Cost Summary (AWS Demo, us-east-1)

| Resource | Type | Unit Cost | 2-Week Sprint (work hours) |
|----------|------|-----------|---------------------------|
| Monitoring EC2 | t3.large | $0.0832/hr | $8.32 |
| Backend EC2 | t3.small | $0.0208/hr | $2.08 |
| Network EC2 | t3.small | $0.0208/hr | $2.08 |
| AI/LLM EC2 | g4dn.xlarge | $0.526/hr | $52.60 |
| RDS MySQL | db.t3.micro | $0.017/hr | $1.70 |
| S3 + CloudFront | — | — | ~$0.50 |
| EBS + RDS storage | 160 GB total | $0.08/GB | ~$12.80 |
| Elastic IPs + data transfer | — | — | ~$2.00 |
| **Total (work hours, 100 hrs)** | | | **~$82** |
| **Total (24/7, 2 weeks)** | | | **~$240** |

Full cost breakdown and controls documented in `docs/aws-cost-justification.md`.

---

## 11. Provisioning and Deployment

### 11.1 Terraform (Infrastructure)

```
terraform/
  ├── main.tf              # VPC, subnets, NAT gateway, EC2 instances, RDS, S3, CloudFront
  ├── variables.tf         # Instance types, region, CIDR blocks, tags
  ├── outputs.tf           # Instance IPs, RDS endpoint, S3 bucket, CloudFront domain
  ├── security-groups.tf   # sg-monitoring, sg-backend, sg-network, sg-ai, sg-rds
  └── terraform.tfvars     # Environment-specific values
```

`terraform apply` creates all AWS resources. `terraform destroy` removes everything.

### 11.2 Ansible (Configuration)

Existing Ansible playbooks configure services on the EC2 instances. Terraform outputs feed the Ansible inventory:

```
terraform output → inventory/production.yml
  ansible-playbook playbooks/site.yml
```

### 11.3 Deployment Order

1. `terraform apply` — provisions VPC, EC2s, RDS, S3, CloudFront
2. Build React frontend → upload to S3
3. `ansible-playbook playbooks/monitoring.yml` — deploy observability stack
4. `ansible-playbook playbooks/application.yml` — deploy Spring Boot (pointing at RDS)
5. `ansible-playbook playbooks/network.yml` — deploy Kong (routes to backend EC2 + CloudFront)
6. `ansible-playbook playbooks/ai.yml` — deploy Ollama, triage service, MCP servers
7. Configure Grafana alert rules and webhook contact point
8. Seed Drain3 with known-good baseline
9. Run load test to verify end-to-end flow
