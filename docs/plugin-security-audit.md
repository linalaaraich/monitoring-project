# Plugin and Extension Security Audit

**Project:** CIRES Technologies Observability Platform with AI-Powered RCA
**Date:** 2026-03-30
**Audience:** NOC team, DevOps, Security reviewers, Supervisors
**Purpose:** Complete audit of every plugin, extension, agent, and third-party dependency in the observability stack — addressing concerns about plugin trust, developer burden, and security posture at company-wide scale.

---

## 1. Executive Summary

| Question | Answer |
|----------|--------|
| How many third-party plugins does the system use? | **Zero.** Every "plugin" in the stack is either built into the product by its maintainer or is a standalone CNCF/industry-standard service. |
| Do developers need to write plugins? | **No.** Adding a new service to monitoring requires only YAML configuration changes. No code, no plugins. |
| What custom code does the team write? | Two standalone Python services (triage service + MCP servers) that run in their own containers. These are independent services, not plugins injected into other systems. |
| What's the supply chain trust level? | Every component is maintained by CNCF graduated/incubating projects, major tech companies (Google, IBM, Kong Inc., Grafana Labs), or the OpenTelemetry project. No community marketplace plugins are used. |

---

## 2. Component-by-Component Audit

### 2.1 Prometheus (Metrics Collection)

| Property | Detail |
|----------|--------|
| **Role** | Scrapes metrics from all services via HTTP `/metrics` endpoints |
| **Plugins used** | None |
| **How it works** | Prometheus pulls metrics from targets over HTTP. Targets expose a standard `/metrics` endpoint. No plugin is installed on either side — Prometheus reads, targets serve. |
| **Configuration** | YAML scrape config listing target addresses and ports |
| **Security** | Runs in private VPC. Scrape targets are internal IPs only. No authentication needed for internal metrics endpoints in the demo; production should add TLS + basic auth on scrape targets. |
| **Maintainer** | CNCF Graduated Project (Prometheus Authors) |

**What devs do to add a new service:** Add 3 lines of YAML to the Prometheus scrape config with the service's IP and port. Zero code changes.

---

### 2.2 Grafana (Dashboards + Alerting)

| Property | Detail |
|----------|--------|
| **Role** | Visualization dashboards, alert rule evaluation, webhook delivery to triage service |
| **Plugins used** | **None.** Prometheus, Loki, and Jaeger data sources are built into Grafana core. |
| **Third-party marketplace plugins** | **None installed.** The architecture deliberately avoids Grafana marketplace plugins to eliminate supply chain risk. |
| **Alerting** | Uses Grafana's built-in Unified Alerting (replaces Alertmanager). Alert rules evaluate against Prometheus and Loki data sources. A single webhook contact point sends alerts to the triage service. No email contact point in Grafana — email is handled by the triage service after AI evaluation. |
| **Security** | Grafana runs in private VPC on the monitoring VM. Admin credentials should be hardened for production. Dashboard provisioning is done via YAML files, not manual UI configuration. |
| **Maintainer** | Grafana Labs (open-source core, AGPLv3) |

**What devs do:** Nothing. Dashboards and alert rules are managed by the observability team via YAML provisioning or the Grafana UI. Developers don't interact with Grafana plugins at all.

---

### 2.3 Loki (Log Storage)

| Property | Detail |
|----------|--------|
| **Role** | Receives logs from OTel Collector, stores and indexes them for querying |
| **Plugins used** | None |
| **How it works** | Loki exposes an HTTP API. OTel Collector pushes logs to it. Grafana queries it. No plugins on any side. |
| **Storage** | TSDB on local disk (EBS in AWS). No external plugin for storage backend in the demo. Production could use S3 for chunk storage (built-in Loki capability, not a plugin). |
| **Security** | Runs in private VPC. Accepts pushes only from known OTel Collector instances. No public exposure. |
| **Maintainer** | Grafana Labs (open-source, AGPLv3) |

---

### 2.4 Jaeger (Distributed Tracing)

| Property | Detail |
|----------|--------|
| **Role** | Receives traces from OTel Collector, stores and visualizes them |
| **Plugins used** | None |
| **How it works** | Jaeger v2 receives traces via OTLP protocol (industry standard). OTel Collector exports to Jaeger over gRPC. No plugins involved. |
| **Storage** | Badger (embedded key-value store) on local disk. No external storage plugin for the demo. |
| **Security** | OTLP ports (4327/4328) are internal only. UI port (16686) accessible via Grafana cross-linking. Runs in private VPC. |
| **Maintainer** | CNCF Graduated Project (Jaeger Authors, originally Uber) |

---

### 2.5 OpenTelemetry Collector (Telemetry Pipeline)

| Property | Detail |
|----------|--------|
| **Role** | Central telemetry pipeline — receives traces from Kong and Spring Boot, ships logs from files to Loki, forwards traces to Jaeger |
| **Components used** | Receivers (OTLP, filelog), processors (batch, resource), exporters (otlp, loki) |
| **Are these plugins?** | **No.** These are built-in components of the `otel/opentelemetry-collector-contrib` distribution. They ship with the official Docker image. Nothing is downloaded, installed, or injected at runtime. |
| **Custom components** | **None.** The architecture uses only standard components from the official contrib distribution. |
| **Configuration** | A single YAML config file defining receivers, processors, and exporters. Declarative, no code. |
| **Security** | OTLP receivers listen on internal ports only (4317 gRPC, 4318 HTTP). The filelog receiver reads local container log files via Docker volume mounts — no network exposure. All data stays within the VPC. |
| **Maintainer** | CNCF Graduated Project (OpenTelemetry — backed by Google, Microsoft, Splunk, Datadog, and others) |

**What devs do to add a new service's logs:** Add the log file path to the OTel Collector's filelog receiver config (2-3 lines of YAML). No code, no plugin.

---

### 2.6 Kong API Gateway

| Property | Detail |
|----------|--------|
| **Role** | API gateway — routes traffic, propagates trace context, exposes Prometheus metrics |
| **Plugins used** | **2 — both first-party, built into Kong** |

#### Kong Plugin Detail

| Plugin | Type | Source | What it does | Security |
|--------|------|--------|-------------|----------|
| **OpenTelemetry** | First-party, ships with Kong | Kong Inc. (bundled in official image) | Injects W3C Trace Context headers into requests, sends trace spans to OTel Collector via OTLP/HTTP | Outbound connection to internal OTel Collector only. No data leaves VPC. |
| **Prometheus** | First-party, ships with Kong | Kong Inc. (bundled in official image) | Exposes Kong metrics (request count, latency, bandwidth) on `/metrics` endpoint for Prometheus to scrape | Read-only metrics endpoint. Internal network only. |

**Important:** These are **not** third-party marketplace plugins. They are part of Kong's official distribution, maintained by Kong Inc., included in every Kong Docker image. They require zero installation — only declarative YAML configuration to enable them.

**No other Kong plugins are used.** No custom Lua plugins, no community plugins, no Kong marketplace installs.

---

### 2.7 OpenTelemetry Java Agent (Spring Boot Instrumentation)

| Property | Detail |
|----------|--------|
| **Role** | Automatically instruments Spring Boot for distributed tracing and JDBC query tracing |
| **Is it a plugin?** | **No.** It's a JVM agent attached via the `-javaagent` flag at startup. It uses standard Java bytecode instrumentation (same mechanism as debuggers and profilers). |
| **Code changes required** | **Zero.** The agent attaches externally. The Spring Boot application source code is not modified in any way. |
| **What it captures** | HTTP requests/responses, Spring MVC controller spans, JDBC queries (including full SQL), connection pool metrics, JVM metrics |
| **JDBC tracing** | Every SQL query from Spring Boot to MySQL/RDS appears as a child span with: query text, execution time, database name, connection details. This is how database operations are traced without any MySQL-side plugin. |
| **Propagation** | W3C Trace Context + B3 multi-header (compatible with Kong's OTel plugin) |
| **Configuration** | Environment variables in docker-compose (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_PROPAGATORS`). No config files inside the application. |
| **Security** | The agent sends traces to the OTel Collector on the internal network only. No external endpoints. The agent JAR is downloaded once at build time from the official Maven Central repository (checksum-verified). |
| **Maintainer** | OpenTelemetry Project (CNCF Graduated) |

**What devs do to instrument a new Java service:** Add one line to the Dockerfile (`-javaagent:/otel-agent.jar`) and set 3 environment variables. Zero application code changes.

---

### 2.8 Standard Exporters

| Exporter | Role | Plugin? | Maintainer |
|----------|------|---------|------------|
| **node_exporter** | Exports Linux host metrics (CPU, RAM, disk, network) | No — standalone binary running in its own container | Prometheus Project (CNCF) |
| **cAdvisor** | Exports Docker container metrics (CPU, RAM, network per container) | No — standalone container by Google | Google |
| **MySQL Exporter** | Exports MySQL metrics (queries/sec, connections, replication lag) | No — standalone binary connecting to MySQL via standard SQL protocol | Prometheus Community |

None of these are plugins. They are independent processes that read system/service state and expose it as Prometheus metrics. They don't modify or inject into the systems they monitor.

---

### 2.9 Drain3 (Log Anomaly Detection)

| Property | Detail |
|----------|--------|
| **Role** | Unsupervised log template mining and anomaly detection (Layer 1 detection) |
| **Is it a plugin?** | **No.** It's a Python library (`pip install drain3`) that runs in-process inside the FastAPI triage service. |
| **How it works** | Drain3 parses log lines into templates using an online streaming algorithm. New/unknown templates are flagged as anomalies. It learns continuously from incoming logs. |
| **State persistence** | Drain3's learned model state is serialized to S3 (baseline snapshots). Periodic automated reset and re-seed from known-good snapshots prevents baseline drift. |
| **MCP exposure** | The Drain3 MCP server gives the LLM read-only access to cluster stats, anomaly rates, and pattern classification. The LLM cannot modify Drain3's state. |
| **Security** | Runs entirely in-process on the AI/LLM VM. No network listener. State snapshots on S3 are encrypted at rest. No external API calls. |
| **Maintainer** | IBM Research (open-source, published algorithm with peer-reviewed papers) |

---

### 2.10 Ollama (Self-Hosted LLM)

| Property | Detail |
|----------|--------|
| **Role** | Local LLM inference for root cause analysis (Layer 3) |
| **Plugins used** | None |
| **Is it a plugin?** | **No.** Standalone service running on port 11434. The triage service calls it via HTTP API. |
| **Models** | Llama 3 8B or Mistral 7B (quantized). Downloaded once, stored locally. |
| **Security** | **No data leaves the infrastructure.** Ollama runs entirely on the AI/LLM VM within the private VPC. Port 11434 is accessible only from the private subnet. No external API calls, no telemetry, no cloud inference. This is a hard requirement per CIRES data policy. |
| **Maintainer** | Ollama Inc. (open-source, MIT license) |

---

### 2.11 MCP Servers (Model Context Protocol Bridges)

| Property | Detail |
|----------|--------|
| **Role** | Give the LLM structured access to monitoring data sources |
| **Are these plugins?** | **No.** They are standalone FastAPI Python services running in their own containers. They wrap existing HTTP APIs (Prometheus, Loki, Jaeger, Drain3 state, RCA history). |
| **Custom code?** | **Yes — written by the team in Sprint 2.** These are the only custom services besides the triage service itself. |
| **What they expose** | Read-only query interfaces. The LLM can query metrics, search logs, find traces, check anomaly rates, and review past RCA decisions. It cannot modify any data source. |
| **Security** | Internal network only (private subnet). No public exposure. Read-only access to data sources. Each MCP server has scoped access to exactly one data source — no cross-access. |

| MCP Server | Data Source | Access Level | Custom Code |
|------------|------------|-------------|-------------|
| Prometheus MCP | Prometheus HTTP API | Read-only queries | ~100 lines Python |
| Loki MCP | Loki HTTP API | Read-only log search | ~100 lines Python |
| Jaeger MCP | Jaeger HTTP API | Read-only trace search | ~100 lines Python |
| Drain3 MCP | Drain3 in-memory state | Read-only cluster stats | ~80 lines Python |
| RCA History MCP | Triage service SQLite DB | Read-only past decisions | ~80 lines Python |

**Total custom code for all 5 MCP servers: ~460 lines of Python.** These are thin wrappers, not complex systems.

---

### 2.12 FastAPI Triage Service

| Property | Detail |
|----------|--------|
| **Role** | Central decision-making service (Layer 2). Receives alert webhooks, coordinates triage, calls LLM, sends email notifications. |
| **Is it a plugin?** | **No.** Standalone FastAPI service in its own container on port 8090. |
| **Custom code?** | **Yes — written by the team in Sprint 2.** This is the core Sprint 2 deliverable. |
| **Dependencies** | `fastapi`, `uvicorn`, `drain3`, `httpx`, `smtplib` (standard library). All well-known, widely-used Python packages. |
| **Security** | Receives webhooks from Grafana (internal). Calls Ollama (internal). Sends email via SMTP (outbound only). Stores RCA history in local SQLite. No public API exposure. |

---

## 3. Plugin Count Summary

| Category | Count | Details |
|----------|-------|---------|
| **Third-party / marketplace plugins** | **0** | None in any component |
| **First-party built-in plugins** | **2** | Kong OTel + Kong Prometheus (both ship with Kong, maintained by Kong Inc.) |
| **Standalone agents (not plugins)** | **3** | node_exporter, cAdvisor, MySQL Exporter |
| **JVM agents (not plugins)** | **1** | OTel Java Agent (external attachment, zero code changes) |
| **Custom services written by the team** | **2** | Triage Service + MCP Servers (standalone containers, ~600 lines total) |
| **Libraries used in custom services** | **1** | Drain3 (in-process Python library by IBM Research) |

---

## 4. Scaling to Company-Wide Infrastructure

When the platform monitors the entire CIRES infrastructure (not just the demo app), here's what's needed per new service:

### 4.1 Adding a New Service to Monitoring

| What | How | Effort | Plugin needed? |
|------|-----|--------|---------------|
| **Metrics** | Service exposes `/metrics` endpoint (most frameworks have this built-in: Spring Boot Actuator, Express prom-client, etc.) | Add 3 lines to Prometheus scrape config | No |
| **Logs** | OTel Collector filelog receiver reads the service's log files | Add file path to OTel Collector config | No |
| **Traces (Java)** | Attach OTel Java Agent via `-javaagent` JVM flag | 1 Dockerfile line + 3 env vars | No — zero code changes |
| **Traces (Python)** | Install `opentelemetry-instrumentation` + 3 lines at startup | pip install + 3 lines | No plugin — standard library |
| **Traces (Node.js)** | Install `@opentelemetry/auto-instrumentations-node` + require at startup | npm install + 1 line | No plugin — standard library |
| **Traces (Go)** | OTel Go SDK + HTTP/gRPC middleware | Middleware wrapping in main.go | No plugin — SDK integration |
| **Traces (.NET)** | OTel .NET auto-instrumentation | NuGet package + 3 lines | No plugin — standard library |
| **Dashboard** | Add panels in Grafana | UI or YAML provisioning | No |
| **Alerts** | Add rules in Grafana Alerting | UI or YAML provisioning | No |

### 4.2 What Developers Never Need to Do

- Write Grafana plugins
- Write Prometheus exporters (unless monitoring proprietary protocols — unlikely)
- Write OTel Collector components
- Write Kong plugins
- Install any marketplace/community plugins
- Modify the observability stack itself

### 4.3 Scaling the Stack Itself

| Concern | Solution | Plugin needed? |
|---------|----------|---------------|
| Prometheus storage grows | Enable remote write to Thanos or Mimir (built-in Prometheus capability) | No |
| Loki storage grows | Switch chunk storage to S3 (built-in Loki capability) | No |
| Need more OTel Collectors | Deploy additional instances behind a load balancer | No |
| Need HA for Grafana | Deploy multiple Grafana instances with shared PostgreSQL backend (built-in) | No |
| Need to monitor Kubernetes workloads | Add Prometheus ServiceMonitor CRDs (standard Kubernetes operator pattern) | No |

---

## 5. Security Posture

### 5.1 Supply Chain Trust

| Component | Maintainer | Governance | Trust Signal |
|-----------|-----------|------------|-------------|
| Prometheus | Prometheus Authors | CNCF Graduated | Industry standard since 2016. Used by >50% of Kubernetes deployments. |
| Grafana | Grafana Labs | Open-source (AGPLv3) | Used by 1M+ organizations. Enterprise version available. |
| Loki | Grafana Labs | Open-source (AGPLv3) | Same maintainer as Grafana. Widely adopted. |
| Jaeger | Jaeger Authors | CNCF Graduated | Originally built by Uber for production tracing at scale. |
| OTel Collector | OpenTelemetry | CNCF Graduated | Backed by Google, Microsoft, Splunk, Datadog, Lightstep. The emerging industry standard for telemetry. |
| OTel Java Agent | OpenTelemetry | CNCF Graduated | Same governance as OTel Collector. Published on Maven Central with checksums. |
| Kong | Kong Inc. | Open-source (Apache 2.0) | Used by Fortune 500 companies. Enterprise version available. |
| node_exporter | Prometheus Authors | CNCF | Standard Linux metrics exporter since 2014. |
| cAdvisor | Google | Open-source (Apache 2.0) | Built by Google for their internal container monitoring. |
| Drain3 | IBM Research | Open-source (MIT) | Peer-reviewed algorithm (ICDE 2017). Used in IBM Watson AIOps. |
| Ollama | Ollama Inc. | Open-source (MIT) | Local-only inference. No telemetry. No cloud dependency. |

### 5.2 Network Security

| Boundary | Policy |
|----------|--------|
| **Public internet → VPC** | Only CloudFront (frontend CDN) and SSH (restricted to CIRES IPs) are publicly accessible. All monitoring, tracing, and AI services are internal only. |
| **Between VMs** | Security groups restrict traffic to required ports only. Each VM accepts connections only from known peers. |
| **RDS** | Private subnet only. No public endpoint. Accessible only from backend EC2 security group. |
| **AI/LLM VM** | Ollama (11434) and triage service (8090) accessible only from private subnet. No public exposure. |
| **MCP servers** | Internal only. Each scoped to one data source. Read-only access. |
| **OTel data** | All telemetry (traces, metrics, logs) flows over internal network. No telemetry data leaves the VPC. |
| **LLM inference** | **Entirely local.** No data sent to external AI APIs. Hard requirement per CIRES data policy. |

### 5.3 Data Flow Security

```
External traffic → CloudFront (HTTPS) → Kong (internal) → Spring Boot (internal) → RDS (private subnet)
                                                    ↓
                                         OTel Collector (internal)
                                                    ↓
                                    Prometheus / Loki / Jaeger (internal)
                                                    ↓
                                         Grafana Alerting (internal)
                                                    ↓
                                         Triage Service (internal)
                                                    ↓
                                         Ollama LLM (internal, local-only)
                                                    ↓
                                         Email to devs (outbound SMTP only)
```

Every arrow above is internal except the first (CloudFront) and the last (SMTP email). No monitoring data, no traces, no logs, no LLM queries ever leave the VPC.

---

## 6. Summary for the NOC Team

> **The observability platform uses zero third-party plugins.** The only "plugins" in the entire stack are two built-in Kong capabilities (OpenTelemetry and Prometheus) that ship with every Kong installation and are maintained by Kong Inc.
>
> **Developers will never write plugins.** To add a new service to monitoring, they add a few lines of YAML configuration. For distributed tracing in Java services, they add one JVM flag — zero application code changes. For other languages, they add a standard OpenTelemetry SDK (a library, not a plugin).
>
> **The two custom services** (triage service and MCP servers) are standalone Python containers totaling ~600 lines of code. They communicate over internal HTTP APIs. They are not injected into or dependent on any other system.
>
> **Every component is maintained by CNCF graduated projects, major tech companies, or established open-source organizations.** No community marketplace plugins, no unvetted dependencies, no custom extensions to core systems.
>
> **All data stays internal.** No monitoring data or LLM queries leave the company-controlled infrastructure.
