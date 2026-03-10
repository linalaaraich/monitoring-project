# Observability Platform — CIRES Technologies Digital Factory

## Project Overview

AI-enhanced observability platform for CIRES Technologies' private cloud infrastructure at Tanger Med. Covers all three pillars of observability (metrics, logs, distributed tracing) plus a Grafana unified dashboard, with an AI layer for automated root cause analysis.

**Intern:** LAARAICH Lina (DevOps/PFE)
**Supervisor:** M. El Hamouchi Yousra
**Duration:** 4 months

---

## Infrastructure

### VM Layout

| VM | Role | IP | OS |
|---|---|---|---|
| VM1 | Monitoring (all observability services) | 192.168.127.10 | Ubuntu Server 24.04 |
| VM2 | Network (API gateway) | 192.168.127.15 | Ubuntu Server 24.04 |
| VM3 | Application (the system under observation) | 192.168.127.30 | Ubuntu Server 24.04 |
| Control | Ansible control node | 192.168.127.20 | Ubuntu Server 24.04 |

- **Hypervisor:** VMware Workstation Pro 17
- **Network:** NAT subnet 192.168.127.0/24
- **Host machine:** 24 GB RAM, 8 cores

### Application Under Test

The monitored application is `mukundmadhav/react-springboot-mysql` — a React frontend + Spring Boot REST API + MySQL database. It has **zero built-in observability**. All instrumentation is injected externally via OpenTelemetry Java agent and exporters.

---

## Complete Service Map

### VM1 — Monitoring (192.168.127.10)

#### Core Observability Stack

| Service | Port | Purpose |
|---|---|---|
| Prometheus | :9090 | Metrics collection. Pull-based scrape from all VMs every 15s. PromQL engine. |
| Loki | :3100 | Log aggregation. Receives push from Promtail agents on all VMs. Label-indexed, compressed chunks. LogQL engine. |
| Jaeger (all-in-one v2) | :16686 (UI), :4317 (OTLP gRPC), :4318 (OTLP HTTP) | Distributed tracing. Receives spans via OTLP. Stores in Badger. Query API + UI. |
| OTel Collector | :4317 (OTLP gRPC) | Central telemetry hub. Receives OTLP from instrumented apps, batches/processes, exports to Jaeger. Note: OTel Collector is OPTIONAL — the OTel Java agent can export directly to Jaeger's OTLP endpoint. See "Trace Pipeline Options" below. |
| Grafana | :3000 | Unified dashboards across Prometheus + Loki + Jaeger datasources. Grafana Alerting with webhook contact point (alerts go to LLM triage, NOT to humans directly). |

#### AI-Enhanced Layer (future — post-demo)

| Service | Port | Purpose |
|---|---|---|
| Drain3 Anomaly Detector | — | Consumes Loki log stream, mines log templates, detects new patterns and frequency anomalies |
| LLM Triage Service | :8090 | Webhook receiver for Grafana alerts + Drain3 events. Queues alerts, triggers LLM investigation, decides escalate or dismiss. 5-min timeout fallback: if LLM unresponsive, raw alert passes through to team. |
| MCP Servers (4) | — | Prometheus MCP, Loki MCP, Jaeger MCP, System Metadata MCP. Structured read-only access for the LLM. |
| Ollama / vLLM | :11434 | Self-hosted LLM (Llama 3.1 / Mistral / Qwen 70B 4-bit). OpenAI-compatible API. |

#### Agents on VM1

| Agent | Port | Purpose |
|---|---|---|
| node_exporter | :9100 | Host metrics (CPU, RAM, disk, network) |
| cAdvisor | :8081 | Container metrics |
| Promtail | — | Ships monitoring service logs back into Loki (self-monitoring) |

### VM2 — Network (192.168.127.15)

| Service | Port | Purpose |
|---|---|---|
| Kong Gateway | :8000 | API gateway. Routes external traffic to application services on .30 |
| Kong Admin API | :8001 | Configuration endpoint. Also exposes /metrics for Prometheus. |

#### Kong Plugins

| Plugin | Purpose |
|---|---|
| prometheus | Exposes request rates, latency histograms, status code counts at :8001/metrics |
| opentelemetry | Generates traces for every request passing through Kong. Exports OTLP to .10:4317 |
| http-log | HTTP access logging |
| correlation-id | Injects X-Correlation-ID header for request tracking |

#### Agents on VM2

| Agent | Port | Purpose |
|---|---|---|
| node_exporter | :9100 | Host metrics |
| cAdvisor | :8081 | Container metrics |
| Promtail | — | Ships Kong logs to .10:3100 |

### VM3 — Application (192.168.127.30)

| Service | Port | Purpose |
|---|---|---|
| React Frontend | :8080 | UI served via nginx or node |
| Spring Boot API | :8080 (or :8082 — check docker-compose) | REST backend. **Instrumented with OTel Java agent.** |
| MySQL | :3306 | Database |

#### Instrumentation on VM3

| Agent | Port | Purpose |
|---|---|---|
| OpenTelemetry Java Agent | — | Attached to Spring Boot JVM via `-javaagent`. Auto-instruments HTTP requests, JDBC calls, Spring annotations. Generates spans + injects trace_id into log MDC. Exports OTLP to .10:4317 |
| MySQL Exporter | :9104 | MySQL metrics for Prometheus (connections, queries, buffer pool, replication) |
| node_exporter | :9100 | Host metrics |
| cAdvisor | :8081 | Container metrics |
| Promtail | — | Ships application logs to .10:3100 |

### Ansible Control Node (192.168.127.20)

| Component | Detail |
|---|---|
| Ansible | Deploys and configures all VMs |
| SSH user | `deploy` (NOPASSWD sudo on all managed nodes) |
| SSH key | `~/.ssh/ansible_key` (ed25519, no passphrase) |
| node_exporter | :9100 (also monitored) |
| Promtail | Ships its own logs to .10:3100 |

---

## Ansible Project Structure

```
monitoring-project/
├── ansible.cfg
├── files/
├── inventory/
│   ├── int.yml                    # Inventory file
│   └── group_vars/
│       ├── all.yml                # Variables for ALL hosts
│       ├── monitoring.yml         # Variables for monitoring group
│       ├── application.yml        # Variables for application group
│       └── network.yml            # Variables for network group
├── playbooks/
│   ├── site.yml                   # Master playbook (runs all)
│   ├── monitoring.yml             # Monitoring VM playbook
│   ├── application.yml            # Application VM playbook
│   └── network.yml                # Network VM playbook
└── roles/
    ├── common/                    # Docker, node_exporter, Promtail, cAdvisor
    ├── docker/                    # Docker CE + Docker Compose installation
    ├── prometheus/                # Prometheus server + scrape config
    ├── loki/                      # Loki server
    ├── jaeger/                    # Jaeger all-in-one v2 with Badger
    ├── otel-collector/            # OpenTelemetry Collector (optional)
    ├── grafana/                   # Grafana + datasource provisioning
    ├── promtail/                  # Promtail log shipper
    ├── app/                       # React + Spring Boot + MySQL + OTel Java agent
    └── kong/                      # Kong Gateway + plugins
```

### ansible.cfg

```ini
[defaults]
inventory = inventory/int.yml
private_key_file = ~/.ssh/ansible_key
remote_user = deploy
host_key_checking = False       # Set to True after initial setup
forks = 3
pipelining = True               # Reduces SSH connections per task
roles_path = roles
retry_files_enabled = True

[privilege_escalation]
become = True
become_method = sudo
become_ask_pass = False
```

### Inventory (inventory/int.yml)

```yaml
all:
  children:
    monitoring:
      hosts:
        monitoring-vm:
          ansible_host: 192.168.127.10
          ansible_user: deploy
    application:
      hosts:
        application-vm:
          ansible_host: 192.168.127.30
          ansible_user: deploy
          app_port: 8080
    network:
      hosts:
        network-vm:
          ansible_host: 192.168.127.15
          ansible_user: deploy
  vars:
    ansible_python_interpreter: /usr/bin/python3
    ansible_ssh_private_key_file: ~/.ssh/ansible_key
    timezone: "Africa/Casablanca"
    ntp_servers:
      - 0.ma.pool.ntp.org
      - 1.ma.pool.ntp.org
```

### Key Group Variables

#### all.yml (applies to every host)

```yaml
admin_email: laaraichlina@gmail.com
ssh_port: 22
firewall_enabled: true
ansible_control_ip: 192.168.127.20

common_packages:
  - curl
  - wget
  - vim
  - htop
  - net-tools
  - jq
  - unzip
  - ca-certificates
  - gnupg

docker_compose_version: "5.0.1"
cadvisor_port: 8081
node_port: 9100
loki_push_endpoint: "http://192.168.127.10:3100/loki/api/v1/push"
jaeger_endpoint: "http://192.168.127.10:14268/api/traces"
prometheus_host: "192.168.127.10"
```

#### monitoring.yml

```yaml
grafana_port: 3000
prometheus_port: 9090
loki_port: 3100
jaeger_port_ui: 16686
jaeger_port_collector: 14268
badger_data_dir: /data/badger
grafana_admin_password: "admin"   # CHANGE IN PRODUCTION
grafana_datasources:
  - prometheus
  - loki
  - jaeger
prometheus_scrape_interval: "15s"
prometheus_retention_days: 15
loki_retention_days: 7

prometheus_targets:
  # Application VM
  - job: "app-spring-actuator"
    host: "192.168.127.30"
    port: "{{ app_port }}"
  - job: "app-cadvisor"
    host: "192.168.127.30"
    port: "{{ cadvisor_port }}"
  - job: "app-node-exporter"
    host: "192.168.127.30"
    port: "{{ node_port }}"
  # Network VM
  - job: "net-node-exporter"
    host: "192.168.127.15"
    port: "{{ node_port }}"
  - job: "net-kong"
    host: "192.168.127.15"
    port: "{{ kong_admin_port }}"
  - job: "net-cadvisor"
    host: "192.168.127.15"
    port: "{{ cadvisor_port }}"
  # Monitoring VM (self-monitoring)
  - job: "mon-cadvisor"
    host: "192.168.127.10"
    port: "{{ cadvisor_port }}"
  - job: "mon-node-exporter"
    host: "192.168.127.10"
    port: "{{ node_port }}"
```

#### application.yml

```yaml
app_frontend_port: 80
app_backend_port: 8080
app_db_port: 3306
spring_profile: "int"
app_port: 8080

mysql_database: "app-db"
mysql_user: "appuser"
mysql_password: "123456789"        # CHANGE IN PRODUCTION
mysql_root_password: "123456789"   # CHANGE IN PRODUCTION

otel_agent_version: "2.25.0"
otel_agent_jar: "/opt/otel/opentelemetry-javaagent.jar"
otel_service_name: "react-springboot-app"
otel_exporter_endpoint: "http://192.168.127.10:14268/api/traces"

promtail_port: 9080
app_log_path: "/var/log/app/*.log"
```

#### network.yml

```yaml
kong_proxy_port: 8000
kong_admin_port: 8001
kong_config_mode: "dbless"
kong_config_file: /etc/kong/kong.yml

app_backend_host: "192.168.127.30"
app_backend_port: 8080
promtail_port: 9080
kong_log_path: "/var/log/kong/*.log"

kong_plugins:
  - prometheus
  - http-log
  - correlation-id
  # TODO: add opentelemetry plugin
```

---

## Data Flow Pipelines

### Metrics Pipeline

```
node_exporter (all VMs :9100)  ─┐
cAdvisor (all VMs :8081)       ─┤
MySQL Exporter (.30:9104)      ─┼──► Prometheus (.10:9090) ──► TSDB ──► Grafana dashboards
Kong /metrics (.15:8001)       ─┤                                      + Grafana alert rules
Prometheus self (.10:9090)     ─┘
```

### Logs Pipeline

```
App logs (.30)          ─┐
Kong access logs (.15)  ─┤  Promtail     Loki (.10:3100)    Grafana log panels
Monitoring logs (.10)   ─┼──(each VM)──►  ├──────────────►  + LogQL alert rules
System logs (all VMs)   ─┘                │
                                          └──► Drain3 ──► Triage Service (.10:8090)
                                                           (future: AI layer)
```

### Traces Pipeline

```
OTel Java Agent (.30)  ─┐
                        ├──OTLP──► OTel Collector (.10:4317) ──► Jaeger (.10) ──► Badger
Kong OTel Plugin (.15) ─┘          (optional — see below)         └──► Jaeger UI :16686
                                                                  └──► Grafana Jaeger plugin
```

### Alert → Triage → RCA Pipeline (future)

```
Grafana Alert Rules  ─┐
                      ├──webhook──► Triage Service (.10:8090) ──► LLM investigates via MCP
Drain3 events        ─┘                  │
                                         ├──► Real problem: escalate with full RCA to team
                                         ├──► Noise/transient: dismiss + log reason
                                         └──► LLM down (5 min timeout): raw alert to team
```

---

## Prometheus Scrape Targets

All targets that Prometheus on .10 scrapes:

| Job Name | Target | What it scrapes |
|---|---|---|
| `prometheus` | .10:9090/metrics | Prometheus self-monitoring |
| `grafana` | .10:3000/metrics | Grafana internal metrics |
| `loki` | .10:3100/metrics | Loki internal metrics |
| `jaeger` | .10:14269/metrics | Jaeger internal metrics |
| `mon-node-exporter` | .10:9100 | Monitoring VM host metrics |
| `mon-cadvisor` | .10:8081 | Monitoring VM container metrics |
| `app-spring-actuator` | .30:8080/actuator/prometheus | Spring Boot application metrics |
| `app-node-exporter` | .30:9100 | Application VM host metrics |
| `app-cadvisor` | .30:8081 | Application VM container metrics |
| `app-mysql` | .30:9104 | MySQL metrics |
| `net-kong` | .15:8001/metrics | Kong request metrics |
| `net-node-exporter` | .15:9100 | Network VM host metrics |
| `net-cadvisor` | .15:8081 | Network VM container metrics |

---

## DISTRIBUTED TRACING — DEEP DIVE

This is the primary focus area. Everything below explains Jaeger, OpenTelemetry, Badger, and how traces flow through the system.

### What Distributed Tracing Actually Is

When a user makes an HTTP request, it flows through multiple services: Kong (gateway) → Spring Boot (API) → MySQL (database). Without tracing, if the request is slow, you don't know which service caused the delay.

Distributed tracing solves this by:
1. Assigning a unique **trace ID** to each request at the entry point (Kong)
2. Propagating that trace ID through every service via HTTP headers (`traceparent` header in W3C format)
3. Each service reports **spans** — timed operations within that service
4. A backend (Jaeger) collects all spans, groups them by trace ID, and reconstructs the full request flow

### Key Concepts

**Trace:** A complete request journey across all services. Identified by a 128-bit trace ID (e.g., `4bf92f3577b34da6a3ce929d0e0e4736`).

**Span:** A single operation within a trace. Has a name, start time, duration, service name, and optional key-value attributes. Spans can be nested (parent-child) to show call hierarchy.

**Root span:** The first span in a trace — typically created by Kong when the request enters the system.

**Child span:** A span created within another span. E.g., the Spring Boot API processing span is a child of the Kong routing span. The MySQL query span is a child of the Spring Boot span.

**Span context:** The metadata that gets propagated between services — trace ID, span ID, trace flags. Encoded in the `traceparent` HTTP header.

**Example trace structure:**
```
Trace ID: abc123
├── [Kong] POST /api/orders  (12ms total)
│   ├── [Spring Boot] OrderController.create  (10ms)
│   │   ├── [Spring Boot] OrderService.validate  (2ms)
│   │   ├── [JDBC] SELECT * FROM inventory  (3ms)
│   │   └── [JDBC] INSERT INTO orders  (4ms)
```

### OpenTelemetry (OTel) — The Instrumentation Standard

OpenTelemetry is the CNCF standard for generating telemetry data. It provides:
- **APIs and SDKs** for instrumenting code (manual or automatic)
- **The OTLP protocol** for transmitting telemetry data
- **Auto-instrumentation agents** that inject tracing without code changes

#### OTel Java Agent

The OTel Java agent is a JAR file attached to the JVM at startup. It uses bytecode manipulation to automatically instrument:
- HTTP servers (Spring MVC, Servlet)
- HTTP clients (RestTemplate, WebClient, HttpClient)
- Database clients (JDBC — every SQL query becomes a span)
- Message queues (Kafka, RabbitMQ)
- Caching (Redis)
- Logging (injects trace_id and span_id into SLF4J MDC)

**How to attach it to Spring Boot:**

```bash
java -javaagent:/opt/otel/opentelemetry-javaagent.jar \
  -Dotel.service.name=react-springboot-app \
  -Dotel.exporter.otlp.endpoint=http://192.168.127.10:4317 \
  -Dotel.exporter.otlp.protocol=grpc \
  -Dotel.traces.exporter=otlp \
  -Dotel.metrics.exporter=none \
  -Dotel.logs.exporter=none \
  -jar app.jar
```

Or via environment variables in Docker Compose:

```yaml
services:
  spring-boot:
    image: your-app:latest
    environment:
      JAVA_TOOL_OPTIONS: "-javaagent:/opt/otel/opentelemetry-javaagent.jar"
      OTEL_SERVICE_NAME: "react-springboot-app"
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://192.168.127.10:4317"
      OTEL_EXPORTER_OTLP_PROTOCOL: "grpc"
      OTEL_TRACES_EXPORTER: "otlp"
      OTEL_METRICS_EXPORTER: "none"
      OTEL_LOGS_EXPORTER: "none"
    volumes:
      - /opt/otel/opentelemetry-javaagent.jar:/opt/otel/opentelemetry-javaagent.jar:ro
```

**Key environment variables:**

| Variable | Value | Purpose |
|---|---|---|
| `OTEL_SERVICE_NAME` | `react-springboot-app` | Name shown in Jaeger UI for this service |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://192.168.127.10:4317` | Where to send trace data (Jaeger or OTel Collector OTLP endpoint) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | Protocol for OTLP export (grpc or http/protobuf) |
| `OTEL_TRACES_EXPORTER` | `otlp` | Use OTLP exporter for traces |
| `OTEL_METRICS_EXPORTER` | `none` | Disable OTel metrics export (Prometheus handles metrics) |
| `OTEL_LOGS_EXPORTER` | `none` | Disable OTel logs export (Promtail/Loki handles logs) |
| `OTEL_PROPAGATORS` | `tracecontext,baggage` | W3C Trace Context propagation (default, matches Kong OTel plugin) |

**Trace-log correlation:** The OTel Java agent automatically injects `trace_id` and `span_id` into the SLF4J MDC (Mapped Diagnostic Context). If the application uses structured logging (logback with JSON encoder, or a pattern including `%X{trace_id}`), every log line includes the trace ID. This allows Loki queries like `{service="react-springboot-app"} |= "trace_id=abc123"` to find all logs belonging to a specific trace.

### Trace Pipeline Options

There are two valid ways to get traces from the OTel Java agent into Jaeger:

#### Option A: Direct Export (simpler, current setup)

```
OTel Java Agent (.30) ──OTLP──► Jaeger (.10:4317)
Kong OTel Plugin (.15) ──OTLP──► Jaeger (.10:4317)
```

The OTel Java agent exports directly to Jaeger's native OTLP receiver. Jaeger v2 supports OTLP natively — no translation needed.

**Pros:** Fewer moving parts. One less service to deploy and maintain.
**Cons:** No central place to add processing (sampling, enrichment, filtering). Each application must know Jaeger's address.

**application.yml variable for direct export:**
```yaml
otel_exporter_endpoint: "http://192.168.127.10:4317"  # Jaeger's OTLP gRPC port
```

#### Option B: Via OTel Collector (production pattern)

```
OTel Java Agent (.30) ──OTLP──► OTel Collector (.10:4317) ──OTLP──► Jaeger (.10:4318 or internal)
Kong OTel Plugin (.15) ──OTLP──► OTel Collector (.10:4317) ──────►
```

An OTel Collector sits between agents and Jaeger. It receives OTLP, processes spans (batching, sampling, attribute enrichment), and exports to Jaeger.

**Pros:** Central control over sampling rates, span filtering, attribute injection. Can fan-out to multiple backends. Decouples agents from backend — swap Jaeger for Tempo without touching agents.
**Cons:** One more service to deploy and configure.

**For the demo: Option A is fine.** Add OTel Collector later if you need sampling control or multi-backend export.

### Jaeger v2 — Architecture Deep Dive

Jaeger v2 is a major rewrite. The key change: **Jaeger v2 is built on the OpenTelemetry Collector**. The Jaeger v2 binary IS an OTel Collector with Jaeger-specific extensions (Jaeger storage backends, Jaeger Query API, Jaeger UI).

This means Jaeger v2 natively speaks OTLP — no translation, no adapter, no Zipkin compatibility layer needed.

#### Jaeger v2 All-in-One Components

The `jaeger` all-in-one binary runs these components in a single process:

| Component | Purpose |
|---|---|
| OTLP Receiver | Listens on :4317 (gRPC) and :4318 (HTTP) for incoming spans |
| Span Processor | Batches spans before writing to storage |
| Badger Storage | Embedded key-value store for span persistence |
| Query Service | REST + gRPC API for reading traces (used by Jaeger UI and Grafana) |
| Jaeger UI | Web frontend at :16686 |
| Admin/Metrics | Prometheus metrics endpoint at :14269/metrics |

#### Jaeger v2 Ports Reference

| Port | Protocol | Purpose |
|---|---|---|
| 4317 | gRPC | OTLP receiver — this is where agents send trace data |
| 4318 | HTTP | OTLP HTTP receiver (alternative to gRPC) |
| 16686 | HTTP | Jaeger UI and Query API |
| 16685 | gRPC | Jaeger Query gRPC (used by Grafana Jaeger datasource) |
| 14269 | HTTP | Admin port — health check (/), metrics (/metrics) |

**IMPORTANT:** Jaeger v2 no longer uses the old ports (14268 for HTTP collector, 14250 for gRPC collector, 6831/6832 for UDP Thrift). If your `application.yml` still has `otel_exporter_endpoint: "http://192.168.127.10:14268/api/traces"`, that's the OLD Jaeger v1 HTTP format. Update to `http://192.168.127.10:4317` (OTLP gRPC) or `http://192.168.127.10:4318/v1/traces` (OTLP HTTP).

#### Jaeger v2 Configuration

Jaeger v2 uses a YAML config file (not environment variables like v1). The config follows the OTel Collector config format:

```yaml
# jaeger-config.yaml
service:
  extensions: [jaeger_storage, jaeger_query]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [jaeger_storage_exporter]

extensions:
  jaeger_storage:
    backends:
      badger_main:
        badger:
          directories:
            keys: /data/badger/keys
            values: /data/badger/values
          ephemeral: false
          maintenance_interval: 5m
          span_store_ttl: 168h       # 7 days retention

  jaeger_query:
    storage:
      traces: badger_main
    ui:
      config_file: /etc/jaeger/ui-config.json   # optional UI customization

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

processors:
  batch:
    send_batch_size: 10000
    timeout: 5s

exporters:
  jaeger_storage_exporter:
    trace_storage: badger_main
```

**Run with:**
```bash
jaeger --config jaeger-config.yaml
```

**Or in Docker Compose:**
```yaml
services:
  jaeger:
    image: jaegertracing/jaeger:2       # v2 image
    container_name: jaeger
    restart: unless-stopped
    ports:
      - "16686:16686"   # UI
      - "4317:4317"     # OTLP gRPC
      - "4318:4318"     # OTLP HTTP
      - "14269:14269"   # Admin/metrics
    volumes:
      - ./jaeger-config.yaml:/etc/jaeger/config.yaml:ro
      - jaeger_badger_data:/data/badger
    command: ["--config", "/etc/jaeger/config.yaml"]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:14269/"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  jaeger_badger_data:
    driver: local
```

### Badger Storage — Deep Dive

Badger is an embedded key-value store written in Go (by Dgraph). "Embedded" means it runs inside the Jaeger process — no separate database server, no cluster, no network calls for storage.

#### Why Badger (not Elasticsearch, Cassandra, etc.)

| Aspect | Badger | Elasticsearch |
|---|---|---|
| Deployment | Zero — embedded in Jaeger process | Separate cluster (3+ nodes recommended) |
| Resource usage | ~200-500 MB RAM for the Jaeger process | 2+ GB heap per ES node minimum |
| Operational complexity | None — just disk | JVM tuning, shard management, ILM policies |
| Scaling | Single node only | Horizontally scalable |
| Licensing | Apache 2.0 | AGPL/SSPL/ELv2 (complicated history) |
| Best for | Small-medium scale, labs, single-team | Large scale, multi-tenant, full-text search |

For CIRES's lab environment and demo, Badger is the right choice. If trace volume grows significantly in production (thousands of spans/second sustained), consider migrating to Cassandra or OpenSearch. The Jaeger config change is swapping the `jaeger_storage` extension — nothing upstream changes.

#### Badger Directory Structure

```
/data/badger/
├── keys/       # Key index (LSM tree) — small, must be fast (SSD recommended)
└── values/     # Value log (actual span data) — larger, sequential writes
```

#### Badger Configuration Options

| Option | Default | Purpose |
|---|---|---|
| `directories.keys` | required | Path for key index files |
| `directories.values` | required | Path for value log files |
| `ephemeral` | false | If true, data is in-memory only (lost on restart). Use false for persistence. |
| `span_store_ttl` | 72h | How long to keep spans. Old spans are garbage collected. |
| `maintenance_interval` | 5m | How often to run value log GC. Badger's value log grows and needs periodic compaction. |

#### Badger Maintenance

Badger's value log grows over time as old spans expire but disk space isn't immediately reclaimed. The `maintenance_interval` setting runs garbage collection periodically. If disk usage grows unexpectedly:

1. Check `span_store_ttl` — lower it to keep fewer days of data
2. Check `maintenance_interval` — ensure GC is running
3. Monitor disk usage via node_exporter's `node_filesystem_avail_bytes` metric in Prometheus

### Kong OpenTelemetry Plugin

Kong can generate traces for every request passing through the gateway. This creates the root span (entry point) for each trace.

#### Enabling the OTel Plugin on Kong

In Kong's declarative config (`kong.yml` for dbless mode):

```yaml
_format_version: "3.0"

plugins:
  - name: opentelemetry
    config:
      endpoint: "http://192.168.127.10:4317"    # Jaeger or OTel Collector OTLP gRPC
      resource_attributes:
        service.name: "kong-gateway"
      header_type: w3c                           # W3C Trace Context format

services:
  - name: app-service
    url: http://192.168.127.30:8080
    routes:
      - name: app-route
        paths:
          - /api
```

Or via Kong Admin API:

```bash
curl -X POST http://192.168.127.15:8001/plugins \
  --data "name=opentelemetry" \
  --data "config.endpoint=http://192.168.127.10:4317" \
  --data "config.resource_attributes.service.name=kong-gateway" \
  --data "config.header_type=w3c"
```

**Critical: `header_type: w3c`** ensures Kong uses W3C Trace Context (`traceparent` header), which matches the OTel Java agent's default propagator. If these don't match, traces from Kong and traces from Spring Boot won't link together — you'll get separate traces instead of one connected trace.

### Grafana Jaeger Datasource

Grafana connects to Jaeger's Query API to display traces inline with metrics and logs.

#### Provisioning via Ansible

```yaml
# grafana/provisioning/datasources/datasources.yml
apiVersion: 1
datasources:
  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://localhost:16686      # Same VM, so localhost
    isDefault: false
    jsonData:
      tracesToMetrics:
        datasourceUid: prometheus     # Link traces to Prometheus metrics
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        tags:
          - key: service.name
            value: service
      tracesToLogs:
        datasourceUid: loki           # Link traces to Loki logs
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        filterByTraceID: true
        filterBySpanID: false
        tags:
          - key: service.name
            value: service
      nodeGraph:
        enabled: true                 # Service dependency graph
```

The `tracesToLogs` and `tracesToMetrics` settings enable cross-pillar correlation in Grafana: click on a trace span → jump to the related logs in Loki or metrics in Prometheus for that service and time window.

### End-to-End Trace Flow Example

1. User sends `POST /api/orders` to Kong (.15:8000)
2. Kong OTel plugin creates **root span** with trace ID `abc123`, sets `traceparent: 00-abc123-span1-01` header
3. Kong forwards request to Spring Boot (.30:8080) with the `traceparent` header
4. OTel Java agent on Spring Boot reads `traceparent`, creates **child span** under trace `abc123`
5. Spring Boot calls MySQL — OTel agent creates **child spans** for each JDBC query
6. Spring Boot logs include `trace_id=abc123` (injected by OTel into SLF4J MDC)
7. All spans are exported via OTLP to Jaeger (.10:4317)
8. Jaeger stores spans in Badger, indexed by trace ID and service name
9. In Jaeger UI (.10:16686), search by service → see the full trace with timing breakdown
10. In Grafana, click "Explore" → Jaeger datasource → search traces → click span → jump to Loki logs for that trace ID

---

## Ansible Role: jaeger

### Role Structure

```
roles/jaeger/
├── defaults/
│   └── main.yml          # Default variables
├── files/
│   └── ui-config.json    # Optional Jaeger UI customization
├── handlers/
│   └── main.yml          # Restart handler
├── tasks/
│   └── main.yml          # Task list
└── templates/
    ├── docker-compose.yml.j2     # Jaeger Docker Compose
    └── jaeger-config.yaml.j2     # Jaeger v2 config
```

### defaults/main.yml

```yaml
jaeger_version: "2"
jaeger_ui_port: 16686
jaeger_otlp_grpc_port: 4317
jaeger_otlp_http_port: 4318
jaeger_admin_port: 14269
jaeger_data_dir: /data/badger
jaeger_span_ttl: "168h"            # 7 days
jaeger_batch_size: 10000
jaeger_batch_timeout: "5s"
jaeger_maintenance_interval: "5m"
jaeger_config_dir: /etc/jaeger
```

### tasks/main.yml

```yaml
---
- name: Create Jaeger directories
  file:
    path: "{{ item }}"
    state: directory
    owner: root
    group: root
    mode: "0755"
  loop:
    - "{{ jaeger_config_dir }}"
    - "{{ jaeger_data_dir }}"
    - "{{ jaeger_data_dir }}/keys"
    - "{{ jaeger_data_dir }}/values"

- name: Deploy Jaeger v2 config
  template:
    src: jaeger-config.yaml.j2
    dest: "{{ jaeger_config_dir }}/config.yaml"
    mode: "0644"
  notify: restart jaeger

- name: Deploy Jaeger UI config
  copy:
    src: ui-config.json
    dest: "{{ jaeger_config_dir }}/ui-config.json"
    mode: "0644"
  notify: restart jaeger

- name: Deploy Jaeger Docker Compose
  template:
    src: docker-compose.yml.j2
    dest: "{{ jaeger_config_dir }}/docker-compose.yml"
    mode: "0644"
  notify: restart jaeger

- name: Start Jaeger
  community.docker.docker_compose_v2:
    project_src: "{{ jaeger_config_dir }}"
    state: present
  register: jaeger_result

- name: Wait for Jaeger to be healthy
  uri:
    url: "http://localhost:{{ jaeger_admin_port }}/"
    status_code: 200
  retries: 12
  delay: 5
  until: jaeger_health.status == 200
  register: jaeger_health
```

### handlers/main.yml

```yaml
---
- name: restart jaeger
  community.docker.docker_compose_v2:
    project_src: "{{ jaeger_config_dir }}"
    state: restarted
```

### templates/jaeger-config.yaml.j2

```yaml
service:
  extensions: [jaeger_storage, jaeger_query]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [jaeger_storage_exporter]

extensions:
  jaeger_storage:
    backends:
      badger_main:
        badger:
          directories:
            keys: /data/badger/keys
            values: /data/badger/values
          ephemeral: false
          maintenance_interval: {{ jaeger_maintenance_interval }}
          span_store_ttl: {{ jaeger_span_ttl }}

  jaeger_query:
    storage:
      traces: badger_main

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:{{ jaeger_otlp_grpc_port }}"
      http:
        endpoint: "0.0.0.0:{{ jaeger_otlp_http_port }}"

processors:
  batch:
    send_batch_size: {{ jaeger_batch_size }}
    timeout: {{ jaeger_batch_timeout }}

exporters:
  jaeger_storage_exporter:
    trace_storage: badger_main
```

### templates/docker-compose.yml.j2

```yaml
services:
  jaeger:
    image: jaegertracing/jaeger:{{ jaeger_version }}
    container_name: jaeger
    restart: unless-stopped
    ports:
      - "{{ jaeger_ui_port }}:16686"
      - "{{ jaeger_otlp_grpc_port }}:4317"
      - "{{ jaeger_otlp_http_port }}:4318"
      - "{{ jaeger_admin_port }}:14269"
    volumes:
      - {{ jaeger_config_dir }}/config.yaml:/etc/jaeger/config.yaml:ro
      - {{ jaeger_config_dir }}/ui-config.json:/etc/jaeger/ui-config.json:ro
      - {{ jaeger_data_dir }}:/data/badger
    command: ["--config", "/etc/jaeger/config.yaml"]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:14269/"]
      interval: 10s
      timeout: 5s
      retries: 3
```

---

## Verification Checklist

### Traces Working End-to-End

1. **Jaeger is running:** `curl http://192.168.127.10:14269/` returns 200
2. **Jaeger OTLP is listening:** `curl http://192.168.127.10:14269/metrics | grep otelcol_receiver_accepted_spans` shows span count increasing
3. **Kong is generating traces:** Send request through Kong (`curl http://192.168.127.15:8000/api/...`), then check Jaeger UI for service "kong-gateway"
4. **Spring Boot is generating traces:** Check Jaeger UI for service "react-springboot-app"
5. **Traces are connected:** A single trace should show both Kong and Spring Boot spans as parent-child
6. **Trace-log correlation:** Check that Spring Boot logs in Loki contain `trace_id` field matching Jaeger trace IDs
7. **Grafana Jaeger datasource:** Grafana Explore → Jaeger → search by service → traces appear
8. **Cross-pillar links:** In Grafana, clicking a trace span should offer "View logs" (→ Loki) and "View metrics" (→ Prometheus)

### Common Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| No traces in Jaeger UI | OTel agent not attached, wrong endpoint, firewall blocking 4317 | Check Spring Boot logs for OTel agent startup, verify endpoint, check `ufw status` |
| Kong traces and Spring traces are separate (not linked) | Propagation format mismatch | Ensure Kong uses `header_type: w3c` and OTel agent uses `tracecontext` propagator (default) |
| Traces appear but no spans for MySQL queries | OTel agent not instrumenting JDBC | Verify the JDBC driver is standard (not a custom wrapper). Check `-Dotel.instrumentation.jdbc.enabled=true` |
| `trace_id` not in logs | Logging framework not reading MDC | Add `%X{trace_id}` to logback pattern, or use JSON encoder |
| Jaeger shows "no storage backend configured" | Jaeger v2 config missing or wrong path | Verify `--config` flag points to correct YAML, check Jaeger container logs |
| Badger errors about corrupted data | Dirty shutdown, disk full | Stop Jaeger, delete `/data/badger/*`, restart. Data is lost but traces are reconstructed over time. |

---

## Current Status & Priorities

### Done
- [x] VM infrastructure provisioned (VMware Workstation Pro 17)
- [x] Ansible control node configured (SSH keys, inventory, ansible.cfg)
- [x] Ansible connectivity verified (ping all hosts)
- [x] Group variables defined (all.yml, monitoring.yml, application.yml, network.yml)
- [x] Role structure created

### In Progress — CURRENT FOCUS
- [ ] **Jaeger role**: Deploy Jaeger v2 all-in-one with Badger storage
- [ ] **OTel Java agent**: Attach to Spring Boot, verify trace generation
- [ ] **Kong OTel plugin**: Enable and verify trace propagation
- [ ] **Grafana Jaeger datasource**: Provision and verify cross-pillar links

### Next
- [ ] Prometheus role (scrape targets, alert rules)
- [ ] Loki role (server config, retention)
- [ ] Promtail role (log shipping from all VMs)
- [ ] Grafana role (dashboards, alerting, datasource provisioning)
- [ ] Integration testing (full request → trace → log → metric correlation)

### Future (post-demo)
- [ ] Drain3 anomaly detector
- [ ] LLM triage service + MCP servers
- [ ] Self-hosted LLM (Ollama)
- [ ] Grafana alert rules with webhook to triage service

---

## Design Decisions Log

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Metrics backend | Prometheus | Zabbix, VictoriaMetrics | Native Grafana integration, PromQL, pull-based simplicity |
| Log backend | Loki | Elasticsearch | 6x less storage, minimal ops, native Grafana, no JVM tuning |
| Trace backend | Jaeger v2 + Badger | Tempo, Zipkin, Elastic APM | CNCF standard, OTLP native, embedded storage for lab scale |
| Trace storage | Badger (embedded) | Elasticsearch, Cassandra | Zero operational overhead, sufficient for lab/demo scale |
| Visualization | Grafana (single pane) | Kibana, separate UIs | Unified view across all three pillars + alerting in one tool |
| Alerting | Grafana Alerting only | Alertmanager, Kibana alerts | Queries both PromQL and LogQL, webhook output to LLM triage. Alertmanager would be redundant routing brain. |
| Alert routing | Alerts → LLM first | Alerts → humans directly | LLM acts as triage layer, reduces alert fatigue, only real problems reach team |
| First-pass detection | Grafana thresholds + Drain3 | Elastic ML | Zero licensing cost. Grafana catches known failures, Drain3 catches unknown patterns. LLM validates both. |
| Trace propagation | W3C Trace Context | Zipkin B3, Jaeger native | Industry standard, supported by both Kong OTel plugin and OTel Java agent by default |
| Deployment | Docker Compose via Ansible | K8s, bare metal | Right complexity for 4-VM lab. K8s is future target. |
| Config management | Ansible | Terraform, manual | Infrastructure already exists (VMs created manually). Ansible manages config + deployment. Terraform for future IaC. |

---

## References

- [Jaeger v2 Documentation](https://www.jaegertracing.io/docs/latest/)
- [Jaeger v2 Configuration](https://www.jaegertracing.io/docs/latest/configuration/)
- [OpenTelemetry Java Agent](https://opentelemetry.io/docs/zero-code/java/agent/)
- [OTel Java Agent Configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/)
- [Kong OpenTelemetry Plugin](https://docs.konghq.com/hub/kong-inc/opentelemetry/)
- [Grafana Jaeger Datasource](https://grafana.com/docs/grafana/latest/datasources/jaeger/)
- [Badger (Dgraph)](https://github.com/dgraph-io/badger)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)# Observability Platform — CIRES Technologies Digital Factory

## Project Overview

AI-enhanced observability platform for CIRES Technologies' private cloud infrastructure at Tanger Med. Covers all three pillars of observability (metrics, logs, distributed tracing) plus a Grafana unified dashboard, with an AI layer for automated root cause analysis.

**Intern:** LAARAICH Lina (DevOps/PFE)
**Supervisor:** M. El Hamouchi Yousra
**Duration:** 4 months

---

## Infrastructure

### VM Layout

| VM | Role | IP | OS |
|---|---|---|---|
| VM1 | Monitoring (all observability services) | 192.168.127.10 | Ubuntu Server 24.04 |
| VM2 | Network (API gateway) | 192.168.127.15 | Ubuntu Server 24.04 |
| VM3 | Application (the system under observation) | 192.168.127.30 | Ubuntu Server 24.04 |
| Control | Ansible control node | 192.168.127.20 | Ubuntu Server 24.04 |

- **Hypervisor:** VMware Workstation Pro 17
- **Network:** NAT subnet 192.168.127.0/24
- **Host machine:** 24 GB RAM, 8 cores

### Application Under Test

The monitored application is `mukundmadhav/react-springboot-mysql` — a React frontend + Spring Boot REST API + MySQL database. It has **zero built-in observability**. All instrumentation is injected externally via OpenTelemetry Java agent and exporters.

---

## Complete Service Map

### VM1 — Monitoring (192.168.127.10)

#### Core Observability Stack

| Service | Port | Purpose |
|---|---|---|
| Prometheus | :9090 | Metrics collection. Pull-based scrape from all VMs every 15s. PromQL engine. |
| Loki | :3100 | Log aggregation. Receives push from Promtail agents on all VMs. Label-indexed, compressed chunks. LogQL engine. |
| Jaeger (all-in-one v2) | :16686 (UI), :4317 (OTLP gRPC), :4318 (OTLP HTTP) | Distributed tracing. Receives spans via OTLP. Stores in Badger. Query API + UI. |
| OTel Collector | :4317 (OTLP gRPC) | Central telemetry hub. Receives OTLP from instrumented apps, batches/processes, exports to Jaeger. Note: OTel Collector is OPTIONAL — the OTel Java agent can export directly to Jaeger's OTLP endpoint. See "Trace Pipeline Options" below. |
| Grafana | :3000 | Unified dashboards across Prometheus + Loki + Jaeger datasources. Grafana Alerting with webhook contact point (alerts go to LLM triage, NOT to humans directly). |

#### AI-Enhanced Layer (future — post-demo)

| Service | Port | Purpose |
|---|---|---|
| Drain3 Anomaly Detector | — | Consumes Loki log stream, mines log templates, detects new patterns and frequency anomalies |
| LLM Triage Service | :8090 | Webhook receiver for Grafana alerts + Drain3 events. Queues alerts, triggers LLM investigation, decides escalate or dismiss. 5-min timeout fallback: if LLM unresponsive, raw alert passes through to team. |
| MCP Servers (4) | — | Prometheus MCP, Loki MCP, Jaeger MCP, System Metadata MCP. Structured read-only access for the LLM. |
| Ollama / vLLM | :11434 | Self-hosted LLM (Llama 3.1 / Mistral / Qwen 70B 4-bit). OpenAI-compatible API. |

#### Agents on VM1

| Agent | Port | Purpose |
|---|---|---|
| node_exporter | :9100 | Host metrics (CPU, RAM, disk, network) |
| cAdvisor | :8081 | Container metrics |
| Promtail | — | Ships monitoring service logs back into Loki (self-monitoring) |

### VM2 — Network (192.168.127.15)

| Service | Port | Purpose |
|---|---|---|
| Kong Gateway | :8000 | API gateway. Routes external traffic to application services on .30 |
| Kong Admin API | :8001 | Configuration endpoint. Also exposes /metrics for Prometheus. |

#### Kong Plugins

| Plugin | Purpose |
|---|---|
| prometheus | Exposes request rates, latency histograms, status code counts at :8001/metrics |
| opentelemetry | Generates traces for every request passing through Kong. Exports OTLP to .10:4317 |
| http-log | HTTP access logging |
| correlation-id | Injects X-Correlation-ID header for request tracking |

#### Agents on VM2

| Agent | Port | Purpose |
|---|---|---|
| node_exporter | :9100 | Host metrics |
| cAdvisor | :8081 | Container metrics |
| Promtail | — | Ships Kong logs to .10:3100 |

### VM3 — Application (192.168.127.30)

| Service | Port | Purpose |
|---|---|---|
| React Frontend | :8080 | UI served via nginx or node |
| Spring Boot API | :8080 (or :8082 — check docker-compose) | REST backend. **Instrumented with OTel Java agent.** |
| MySQL | :3306 | Database |

#### Instrumentation on VM3

| Agent | Port | Purpose |
|---|---|---|
| OpenTelemetry Java Agent | — | Attached to Spring Boot JVM via `-javaagent`. Auto-instruments HTTP requests, JDBC calls, Spring annotations. Generates spans + injects trace_id into log MDC. Exports OTLP to .10:4317 |
| MySQL Exporter | :9104 | MySQL metrics for Prometheus (connections, queries, buffer pool, replication) |
| node_exporter | :9100 | Host metrics |
| cAdvisor | :8081 | Container metrics |
| Promtail | — | Ships application logs to .10:3100 |

### Ansible Control Node (192.168.127.20)

| Component | Detail |
|---|---|
| Ansible | Deploys and configures all VMs |
| SSH user | `deploy` (NOPASSWD sudo on all managed nodes) |
| SSH key | `~/.ssh/ansible_key` (ed25519, no passphrase) |
| node_exporter | :9100 (also monitored) |
| Promtail | Ships its own logs to .10:3100 |

---

## Ansible Project Structure

```
monitoring-project/
├── ansible.cfg
├── files/
├── inventory/
│   ├── int.yml                    # Inventory file
│   └── group_vars/
│       ├── all.yml                # Variables for ALL hosts
│       ├── monitoring.yml         # Variables for monitoring group
│       ├── application.yml        # Variables for application group
│       └── network.yml            # Variables for network group
├── playbooks/
│   ├── site.yml                   # Master playbook (runs all)
│   ├── monitoring.yml             # Monitoring VM playbook
│   ├── application.yml            # Application VM playbook
│   └── network.yml                # Network VM playbook
└── roles/
    ├── common/                    # Docker, node_exporter, Promtail, cAdvisor
    ├── docker/                    # Docker CE + Docker Compose installation
    ├── prometheus/                # Prometheus server + scrape config
    ├── loki/                      # Loki server
    ├── jaeger/                    # Jaeger all-in-one v2 with Badger
    ├── otel-collector/            # OpenTelemetry Collector (optional)
    ├── grafana/                   # Grafana + datasource provisioning
    ├── promtail/                  # Promtail log shipper
    ├── app/                       # React + Spring Boot + MySQL + OTel Java agent
    └── kong/                      # Kong Gateway + plugins
```

### ansible.cfg

```ini
[defaults]
inventory = inventory/int.yml
private_key_file = ~/.ssh/ansible_key
remote_user = deploy
host_key_checking = False       # Set to True after initial setup
forks = 3
pipelining = True               # Reduces SSH connections per task
roles_path = roles
retry_files_enabled = True

[privilege_escalation]
become = True
become_method = sudo
become_ask_pass = False
```

### Inventory (inventory/int.yml)

```yaml
all:
  children:
    monitoring:
      hosts:
        monitoring-vm:
          ansible_host: 192.168.127.10
          ansible_user: deploy
    application:
      hosts:
        application-vm:
          ansible_host: 192.168.127.30
          ansible_user: deploy
          app_port: 8080
    network:
      hosts:
        network-vm:
          ansible_host: 192.168.127.15
          ansible_user: deploy
  vars:
    ansible_python_interpreter: /usr/bin/python3
    ansible_ssh_private_key_file: ~/.ssh/ansible_key
    timezone: "Africa/Casablanca"
    ntp_servers:
      - 0.ma.pool.ntp.org
      - 1.ma.pool.ntp.org
```

### Key Group Variables

#### all.yml (applies to every host)

```yaml
admin_email: laaraichlina@gmail.com
ssh_port: 22
firewall_enabled: true
ansible_control_ip: 192.168.127.20

common_packages:
  - curl
  - wget
  - vim
  - htop
  - net-tools
  - jq
  - unzip
  - ca-certificates
  - gnupg

docker_compose_version: "5.0.1"
cadvisor_port: 8081
node_port: 9100
loki_push_endpoint: "http://192.168.127.10:3100/loki/api/v1/push"
jaeger_endpoint: "http://192.168.127.10:14268/api/traces"
prometheus_host: "192.168.127.10"
```

#### monitoring.yml

```yaml
grafana_port: 3000
prometheus_port: 9090
loki_port: 3100
jaeger_port_ui: 16686
jaeger_port_collector: 14268
badger_data_dir: /data/badger
grafana_admin_password: "admin"   # CHANGE IN PRODUCTION
grafana_datasources:
  - prometheus
  - loki
  - jaeger
prometheus_scrape_interval: "15s"
prometheus_retention_days: 15
loki_retention_days: 7

prometheus_targets:
  # Application VM
  - job: "app-spring-actuator"
    host: "192.168.127.30"
    port: "{{ app_port }}"
  - job: "app-cadvisor"
    host: "192.168.127.30"
    port: "{{ cadvisor_port }}"
  - job: "app-node-exporter"
    host: "192.168.127.30"
    port: "{{ node_port }}"
  # Network VM
  - job: "net-node-exporter"
    host: "192.168.127.15"
    port: "{{ node_port }}"
  - job: "net-kong"
    host: "192.168.127.15"
    port: "{{ kong_admin_port }}"
  - job: "net-cadvisor"
    host: "192.168.127.15"
    port: "{{ cadvisor_port }}"
  # Monitoring VM (self-monitoring)
  - job: "mon-cadvisor"
    host: "192.168.127.10"
    port: "{{ cadvisor_port }}"
  - job: "mon-node-exporter"
    host: "192.168.127.10"
    port: "{{ node_port }}"
```

#### application.yml

```yaml
app_frontend_port: 80
app_backend_port: 8080
app_db_port: 3306
spring_profile: "int"
app_port: 8080

mysql_database: "app-db"
mysql_user: "appuser"
mysql_password: "123456789"        # CHANGE IN PRODUCTION
mysql_root_password: "123456789"   # CHANGE IN PRODUCTION

otel_agent_version: "2.25.0"
otel_agent_jar: "/opt/otel/opentelemetry-javaagent.jar"
otel_service_name: "react-springboot-app"
otel_exporter_endpoint: "http://192.168.127.10:14268/api/traces"

promtail_port: 9080
app_log_path: "/var/log/app/*.log"
```

#### network.yml

```yaml
kong_proxy_port: 8000
kong_admin_port: 8001
kong_config_mode: "dbless"
kong_config_file: /etc/kong/kong.yml

app_backend_host: "192.168.127.30"
app_backend_port: 8080
promtail_port: 9080
kong_log_path: "/var/log/kong/*.log"

kong_plugins:
  - prometheus
  - http-log
  - correlation-id
  # TODO: add opentelemetry plugin
```

---

## Data Flow Pipelines

### Metrics Pipeline

```
node_exporter (all VMs :9100)  ─┐
cAdvisor (all VMs :8081)       ─┤
MySQL Exporter (.30:9104)      ─┼──► Prometheus (.10:9090) ──► TSDB ──► Grafana dashboards
Kong /metrics (.15:8001)       ─┤                                      + Grafana alert rules
Prometheus self (.10:9090)     ─┘
```

### Logs Pipeline

```
App logs (.30)          ─┐
Kong access logs (.15)  ─┤  Promtail     Loki (.10:3100)    Grafana log panels
Monitoring logs (.10)   ─┼──(each VM)──►  ├──────────────►  + LogQL alert rules
System logs (all VMs)   ─┘                │
                                          └──► Drain3 ──► Triage Service (.10:8090)
                                                           (future: AI layer)
```

### Traces Pipeline

```
OTel Java Agent (.30)  ─┐
                        ├──OTLP──► OTel Collector (.10:4317) ──► Jaeger (.10) ──► Badger
Kong OTel Plugin (.15) ─┘          (optional — see below)         └──► Jaeger UI :16686
                                                                  └──► Grafana Jaeger plugin
```

### Alert → Triage → RCA Pipeline (future)

```
Grafana Alert Rules  ─┐
                      ├──webhook──► Triage Service (.10:8090) ──► LLM investigates via MCP
Drain3 events        ─┘                  │
                                         ├──► Real problem: escalate with full RCA to team
                                         ├──► Noise/transient: dismiss + log reason
                                         └──► LLM down (5 min timeout): raw alert to team
```

---

## Prometheus Scrape Targets

All targets that Prometheus on .10 scrapes:

| Job Name | Target | What it scrapes |
|---|---|---|
| `prometheus` | .10:9090/metrics | Prometheus self-monitoring |
| `grafana` | .10:3000/metrics | Grafana internal metrics |
| `loki` | .10:3100/metrics | Loki internal metrics |
| `jaeger` | .10:14269/metrics | Jaeger internal metrics |
| `mon-node-exporter` | .10:9100 | Monitoring VM host metrics |
| `mon-cadvisor` | .10:8081 | Monitoring VM container metrics |
| `app-spring-actuator` | .30:8080/actuator/prometheus | Spring Boot application metrics |
| `app-node-exporter` | .30:9100 | Application VM host metrics |
| `app-cadvisor` | .30:8081 | Application VM container metrics |
| `app-mysql` | .30:9104 | MySQL metrics |
| `net-kong` | .15:8001/metrics | Kong request metrics |
| `net-node-exporter` | .15:9100 | Network VM host metrics |
| `net-cadvisor` | .15:8081 | Network VM container metrics |

---

## DISTRIBUTED TRACING — DEEP DIVE

This is the primary focus area. Everything below explains Jaeger, OpenTelemetry, Badger, and how traces flow through the system.

### What Distributed Tracing Actually Is

When a user makes an HTTP request, it flows through multiple services: Kong (gateway) → Spring Boot (API) → MySQL (database). Without tracing, if the request is slow, you don't know which service caused the delay.

Distributed tracing solves this by:
1. Assigning a unique **trace ID** to each request at the entry point (Kong)
2. Propagating that trace ID through every service via HTTP headers (`traceparent` header in W3C format)
3. Each service reports **spans** — timed operations within that service
4. A backend (Jaeger) collects all spans, groups them by trace ID, and reconstructs the full request flow

### Key Concepts

**Trace:** A complete request journey across all services. Identified by a 128-bit trace ID (e.g., `4bf92f3577b34da6a3ce929d0e0e4736`).

**Span:** A single operation within a trace. Has a name, start time, duration, service name, and optional key-value attributes. Spans can be nested (parent-child) to show call hierarchy.

**Root span:** The first span in a trace — typically created by Kong when the request enters the system.

**Child span:** A span created within another span. E.g., the Spring Boot API processing span is a child of the Kong routing span. The MySQL query span is a child of the Spring Boot span.

**Span context:** The metadata that gets propagated between services — trace ID, span ID, trace flags. Encoded in the `traceparent` HTTP header.

**Example trace structure:**
```
Trace ID: abc123
├── [Kong] POST /api/orders  (12ms total)
│   ├── [Spring Boot] OrderController.create  (10ms)
│   │   ├── [Spring Boot] OrderService.validate  (2ms)
│   │   ├── [JDBC] SELECT * FROM inventory  (3ms)
│   │   └── [JDBC] INSERT INTO orders  (4ms)
```

### OpenTelemetry (OTel) — The Instrumentation Standard

OpenTelemetry is the CNCF standard for generating telemetry data. It provides:
- **APIs and SDKs** for instrumenting code (manual or automatic)
- **The OTLP protocol** for transmitting telemetry data
- **Auto-instrumentation agents** that inject tracing without code changes

#### OTel Java Agent

The OTel Java agent is a JAR file attached to the JVM at startup. It uses bytecode manipulation to automatically instrument:
- HTTP servers (Spring MVC, Servlet)
- HTTP clients (RestTemplate, WebClient, HttpClient)
- Database clients (JDBC — every SQL query becomes a span)
- Message queues (Kafka, RabbitMQ)
- Caching (Redis)
- Logging (injects trace_id and span_id into SLF4J MDC)

**How to attach it to Spring Boot:**

```bash
java -javaagent:/opt/otel/opentelemetry-javaagent.jar \
  -Dotel.service.name=react-springboot-app \
  -Dotel.exporter.otlp.endpoint=http://192.168.127.10:4317 \
  -Dotel.exporter.otlp.protocol=grpc \
  -Dotel.traces.exporter=otlp \
  -Dotel.metrics.exporter=none \
  -Dotel.logs.exporter=none \
  -jar app.jar
```

Or via environment variables in Docker Compose:

```yaml
services:
  spring-boot:
    image: your-app:latest
    environment:
      JAVA_TOOL_OPTIONS: "-javaagent:/opt/otel/opentelemetry-javaagent.jar"
      OTEL_SERVICE_NAME: "react-springboot-app"
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://192.168.127.10:4317"
      OTEL_EXPORTER_OTLP_PROTOCOL: "grpc"
      OTEL_TRACES_EXPORTER: "otlp"
      OTEL_METRICS_EXPORTER: "none"
      OTEL_LOGS_EXPORTER: "none"
    volumes:
      - /opt/otel/opentelemetry-javaagent.jar:/opt/otel/opentelemetry-javaagent.jar:ro
```

**Key environment variables:**

| Variable | Value | Purpose |
|---|---|---|
| `OTEL_SERVICE_NAME` | `react-springboot-app` | Name shown in Jaeger UI for this service |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://192.168.127.10:4317` | Where to send trace data (Jaeger or OTel Collector OTLP endpoint) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | Protocol for OTLP export (grpc or http/protobuf) |
| `OTEL_TRACES_EXPORTER` | `otlp` | Use OTLP exporter for traces |
| `OTEL_METRICS_EXPORTER` | `none` | Disable OTel metrics export (Prometheus handles metrics) |
| `OTEL_LOGS_EXPORTER` | `none` | Disable OTel logs export (Promtail/Loki handles logs) |
| `OTEL_PROPAGATORS` | `tracecontext,baggage` | W3C Trace Context propagation (default, matches Kong OTel plugin) |

**Trace-log correlation:** The OTel Java agent automatically injects `trace_id` and `span_id` into the SLF4J MDC (Mapped Diagnostic Context). If the application uses structured logging (logback with JSON encoder, or a pattern including `%X{trace_id}`), every log line includes the trace ID. This allows Loki queries like `{service="react-springboot-app"} |= "trace_id=abc123"` to find all logs belonging to a specific trace.

### Trace Pipeline Options

There are two valid ways to get traces from the OTel Java agent into Jaeger:

#### Option A: Direct Export (simpler, current setup)

```
OTel Java Agent (.30) ──OTLP──► Jaeger (.10:4317)
Kong OTel Plugin (.15) ──OTLP──► Jaeger (.10:4317)
```

The OTel Java agent exports directly to Jaeger's native OTLP receiver. Jaeger v2 supports OTLP natively — no translation needed.

**Pros:** Fewer moving parts. One less service to deploy and maintain.
**Cons:** No central place to add processing (sampling, enrichment, filtering). Each application must know Jaeger's address.

**application.yml variable for direct export:**
```yaml
otel_exporter_endpoint: "http://192.168.127.10:4317"  # Jaeger's OTLP gRPC port
```

#### Option B: Via OTel Collector (production pattern)

```
OTel Java Agent (.30) ──OTLP──► OTel Collector (.10:4317) ──OTLP──► Jaeger (.10:4318 or internal)
Kong OTel Plugin (.15) ──OTLP──► OTel Collector (.10:4317) ──────►
```

An OTel Collector sits between agents and Jaeger. It receives OTLP, processes spans (batching, sampling, attribute enrichment), and exports to Jaeger.

**Pros:** Central control over sampling rates, span filtering, attribute injection. Can fan-out to multiple backends. Decouples agents from backend — swap Jaeger for Tempo without touching agents.
**Cons:** One more service to deploy and configure.

**For the demo: Option A is fine.** Add OTel Collector later if you need sampling control or multi-backend export.

### Jaeger v2 — Architecture Deep Dive

Jaeger v2 is a major rewrite. The key change: **Jaeger v2 is built on the OpenTelemetry Collector**. The Jaeger v2 binary IS an OTel Collector with Jaeger-specific extensions (Jaeger storage backends, Jaeger Query API, Jaeger UI).

This means Jaeger v2 natively speaks OTLP — no translation, no adapter, no Zipkin compatibility layer needed.

#### Jaeger v2 All-in-One Components

The `jaeger` all-in-one binary runs these components in a single process:

| Component | Purpose |
|---|---|
| OTLP Receiver | Listens on :4317 (gRPC) and :4318 (HTTP) for incoming spans |
| Span Processor | Batches spans before writing to storage |
| Badger Storage | Embedded key-value store for span persistence |
| Query Service | REST + gRPC API for reading traces (used by Jaeger UI and Grafana) |
| Jaeger UI | Web frontend at :16686 |
| Admin/Metrics | Prometheus metrics endpoint at :14269/metrics |

#### Jaeger v2 Ports Reference

| Port | Protocol | Purpose |
|---|---|---|
| 4317 | gRPC | OTLP receiver — this is where agents send trace data |
| 4318 | HTTP | OTLP HTTP receiver (alternative to gRPC) |
| 16686 | HTTP | Jaeger UI and Query API |
| 16685 | gRPC | Jaeger Query gRPC (used by Grafana Jaeger datasource) |
| 14269 | HTTP | Admin port — health check (/), metrics (/metrics) |

**IMPORTANT:** Jaeger v2 no longer uses the old ports (14268 for HTTP collector, 14250 for gRPC collector, 6831/6832 for UDP Thrift). If your `application.yml` still has `otel_exporter_endpoint: "http://192.168.127.10:14268/api/traces"`, that's the OLD Jaeger v1 HTTP format. Update to `http://192.168.127.10:4317` (OTLP gRPC) or `http://192.168.127.10:4318/v1/traces` (OTLP HTTP).

#### Jaeger v2 Configuration

Jaeger v2 uses a YAML config file (not environment variables like v1). The config follows the OTel Collector config format:

```yaml
# jaeger-config.yaml
service:
  extensions: [jaeger_storage, jaeger_query]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [jaeger_storage_exporter]

extensions:
  jaeger_storage:
    backends:
      badger_main:
        badger:
          directories:
            keys: /data/badger/keys
            values: /data/badger/values
          ephemeral: false
          maintenance_interval: 5m
          span_store_ttl: 168h       # 7 days retention

  jaeger_query:
    storage:
      traces: badger_main
    ui:
      config_file: /etc/jaeger/ui-config.json   # optional UI customization

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

processors:
  batch:
    send_batch_size: 10000
    timeout: 5s

exporters:
  jaeger_storage_exporter:
    trace_storage: badger_main
```

**Run with:**
```bash
jaeger --config jaeger-config.yaml
```

**Or in Docker Compose:**
```yaml
services:
  jaeger:
    image: jaegertracing/jaeger:2       # v2 image
    container_name: jaeger
    restart: unless-stopped
    ports:
      - "16686:16686"   # UI
      - "4317:4317"     # OTLP gRPC
      - "4318:4318"     # OTLP HTTP
      - "14269:14269"   # Admin/metrics
    volumes:
      - ./jaeger-config.yaml:/etc/jaeger/config.yaml:ro
      - jaeger_badger_data:/data/badger
    command: ["--config", "/etc/jaeger/config.yaml"]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:14269/"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  jaeger_badger_data:
    driver: local
```

### Badger Storage — Deep Dive

Badger is an embedded key-value store written in Go (by Dgraph). "Embedded" means it runs inside the Jaeger process — no separate database server, no cluster, no network calls for storage.

#### Why Badger (not Elasticsearch, Cassandra, etc.)

| Aspect | Badger | Elasticsearch |
|---|---|---|
| Deployment | Zero — embedded in Jaeger process | Separate cluster (3+ nodes recommended) |
| Resource usage | ~200-500 MB RAM for the Jaeger process | 2+ GB heap per ES node minimum |
| Operational complexity | None — just disk | JVM tuning, shard management, ILM policies |
| Scaling | Single node only | Horizontally scalable |
| Licensing | Apache 2.0 | AGPL/SSPL/ELv2 (complicated history) |
| Best for | Small-medium scale, labs, single-team | Large scale, multi-tenant, full-text search |

For CIRES's lab environment and demo, Badger is the right choice. If trace volume grows significantly in production (thousands of spans/second sustained), consider migrating to Cassandra or OpenSearch. The Jaeger config change is swapping the `jaeger_storage` extension — nothing upstream changes.

#### Badger Directory Structure

```
/data/badger/
├── keys/       # Key index (LSM tree) — small, must be fast (SSD recommended)
└── values/     # Value log (actual span data) — larger, sequential writes
```

#### Badger Configuration Options

| Option | Default | Purpose |
|---|---|---|
| `directories.keys` | required | Path for key index files |
| `directories.values` | required | Path for value log files |
| `ephemeral` | false | If true, data is in-memory only (lost on restart). Use false for persistence. |
| `span_store_ttl` | 72h | How long to keep spans. Old spans are garbage collected. |
| `maintenance_interval` | 5m | How often to run value log GC. Badger's value log grows and needs periodic compaction. |

#### Badger Maintenance

Badger's value log grows over time as old spans expire but disk space isn't immediately reclaimed. The `maintenance_interval` setting runs garbage collection periodically. If disk usage grows unexpectedly:

1. Check `span_store_ttl` — lower it to keep fewer days of data
2. Check `maintenance_interval` — ensure GC is running
3. Monitor disk usage via node_exporter's `node_filesystem_avail_bytes` metric in Prometheus

### Kong OpenTelemetry Plugin

Kong can generate traces for every request passing through the gateway. This creates the root span (entry point) for each trace.

#### Enabling the OTel Plugin on Kong

In Kong's declarative config (`kong.yml` for dbless mode):

```yaml
_format_version: "3.0"

plugins:
  - name: opentelemetry
    config:
      endpoint: "http://192.168.127.10:4317"    # Jaeger or OTel Collector OTLP gRPC
      resource_attributes:
        service.name: "kong-gateway"
      header_type: w3c                           # W3C Trace Context format

services:
  - name: app-service
    url: http://192.168.127.30:8080
    routes:
      - name: app-route
        paths:
          - /api
```

Or via Kong Admin API:

```bash
curl -X POST http://192.168.127.15:8001/plugins \
  --data "name=opentelemetry" \
  --data "config.endpoint=http://192.168.127.10:4317" \
  --data "config.resource_attributes.service.name=kong-gateway" \
  --data "config.header_type=w3c"
```

**Critical: `header_type: w3c`** ensures Kong uses W3C Trace Context (`traceparent` header), which matches the OTel Java agent's default propagator. If these don't match, traces from Kong and traces from Spring Boot won't link together — you'll get separate traces instead of one connected trace.

### Grafana Jaeger Datasource

Grafana connects to Jaeger's Query API to display traces inline with metrics and logs.

#### Provisioning via Ansible

```yaml
# grafana/provisioning/datasources/datasources.yml
apiVersion: 1
datasources:
  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://localhost:16686      # Same VM, so localhost
    isDefault: false
    jsonData:
      tracesToMetrics:
        datasourceUid: prometheus     # Link traces to Prometheus metrics
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        tags:
          - key: service.name
            value: service
      tracesToLogs:
        datasourceUid: loki           # Link traces to Loki logs
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        filterByTraceID: true
        filterBySpanID: false
        tags:
          - key: service.name
            value: service
      nodeGraph:
        enabled: true                 # Service dependency graph
```

The `tracesToLogs` and `tracesToMetrics` settings enable cross-pillar correlation in Grafana: click on a trace span → jump to the related logs in Loki or metrics in Prometheus for that service and time window.

### End-to-End Trace Flow Example

1. User sends `POST /api/orders` to Kong (.15:8000)
2. Kong OTel plugin creates **root span** with trace ID `abc123`, sets `traceparent: 00-abc123-span1-01` header
3. Kong forwards request to Spring Boot (.30:8080) with the `traceparent` header
4. OTel Java agent on Spring Boot reads `traceparent`, creates **child span** under trace `abc123`
5. Spring Boot calls MySQL — OTel agent creates **child spans** for each JDBC query
6. Spring Boot logs include `trace_id=abc123` (injected by OTel into SLF4J MDC)
7. All spans are exported via OTLP to Jaeger (.10:4317)
8. Jaeger stores spans in Badger, indexed by trace ID and service name
9. In Jaeger UI (.10:16686), search by service → see the full trace with timing breakdown
10. In Grafana, click "Explore" → Jaeger datasource → search traces → click span → jump to Loki logs for that trace ID

---

## Ansible Role: jaeger

### Role Structure

```
roles/jaeger/
├── defaults/
│   └── main.yml          # Default variables
├── files/
│   └── ui-config.json    # Optional Jaeger UI customization
├── handlers/
│   └── main.yml          # Restart handler
├── tasks/
│   └── main.yml          # Task list
└── templates/
    ├── docker-compose.yml.j2     # Jaeger Docker Compose
    └── jaeger-config.yaml.j2     # Jaeger v2 config
```

### defaults/main.yml

```yaml
jaeger_version: "2"
jaeger_ui_port: 16686
jaeger_otlp_grpc_port: 4317
jaeger_otlp_http_port: 4318
jaeger_admin_port: 14269
jaeger_data_dir: /data/badger
jaeger_span_ttl: "168h"            # 7 days
jaeger_batch_size: 10000
jaeger_batch_timeout: "5s"
jaeger_maintenance_interval: "5m"
jaeger_config_dir: /etc/jaeger
```

### tasks/main.yml

```yaml
---
- name: Create Jaeger directories
  file:
    path: "{{ item }}"
    state: directory
    owner: root
    group: root
    mode: "0755"
  loop:
    - "{{ jaeger_config_dir }}"
    - "{{ jaeger_data_dir }}"
    - "{{ jaeger_data_dir }}/keys"
    - "{{ jaeger_data_dir }}/values"

- name: Deploy Jaeger v2 config
  template:
    src: jaeger-config.yaml.j2
    dest: "{{ jaeger_config_dir }}/config.yaml"
    mode: "0644"
  notify: restart jaeger

- name: Deploy Jaeger UI config
  copy:
    src: ui-config.json
    dest: "{{ jaeger_config_dir }}/ui-config.json"
    mode: "0644"
  notify: restart jaeger

- name: Deploy Jaeger Docker Compose
  template:
    src: docker-compose.yml.j2
    dest: "{{ jaeger_config_dir }}/docker-compose.yml"
    mode: "0644"
  notify: restart jaeger

- name: Start Jaeger
  community.docker.docker_compose_v2:
    project_src: "{{ jaeger_config_dir }}"
    state: present
  register: jaeger_result

- name: Wait for Jaeger to be healthy
  uri:
    url: "http://localhost:{{ jaeger_admin_port }}/"
    status_code: 200
  retries: 12
  delay: 5
  until: jaeger_health.status == 200
  register: jaeger_health
```

### handlers/main.yml

```yaml
---
- name: restart jaeger
  community.docker.docker_compose_v2:
    project_src: "{{ jaeger_config_dir }}"
    state: restarted
```

### templates/jaeger-config.yaml.j2

```yaml
service:
  extensions: [jaeger_storage, jaeger_query]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [jaeger_storage_exporter]

extensions:
  jaeger_storage:
    backends:
      badger_main:
        badger:
          directories:
            keys: /data/badger/keys
            values: /data/badger/values
          ephemeral: false
          maintenance_interval: {{ jaeger_maintenance_interval }}
          span_store_ttl: {{ jaeger_span_ttl }}

  jaeger_query:
    storage:
      traces: badger_main

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:{{ jaeger_otlp_grpc_port }}"
      http:
        endpoint: "0.0.0.0:{{ jaeger_otlp_http_port }}"

processors:
  batch:
    send_batch_size: {{ jaeger_batch_size }}
    timeout: {{ jaeger_batch_timeout }}

exporters:
  jaeger_storage_exporter:
    trace_storage: badger_main
```

### templates/docker-compose.yml.j2

```yaml
services:
  jaeger:
    image: jaegertracing/jaeger:{{ jaeger_version }}
    container_name: jaeger
    restart: unless-stopped
    ports:
      - "{{ jaeger_ui_port }}:16686"
      - "{{ jaeger_otlp_grpc_port }}:4317"
      - "{{ jaeger_otlp_http_port }}:4318"
      - "{{ jaeger_admin_port }}:14269"
    volumes:
      - {{ jaeger_config_dir }}/config.yaml:/etc/jaeger/config.yaml:ro
      - {{ jaeger_config_dir }}/ui-config.json:/etc/jaeger/ui-config.json:ro
      - {{ jaeger_data_dir }}:/data/badger
    command: ["--config", "/etc/jaeger/config.yaml"]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:14269/"]
      interval: 10s
      timeout: 5s
      retries: 3
```

---

## Verification Checklist

### Traces Working End-to-End

1. **Jaeger is running:** `curl http://192.168.127.10:14269/` returns 200
2. **Jaeger OTLP is listening:** `curl http://192.168.127.10:14269/metrics | grep otelcol_receiver_accepted_spans` shows span count increasing
3. **Kong is generating traces:** Send request through Kong (`curl http://192.168.127.15:8000/api/...`), then check Jaeger UI for service "kong-gateway"
4. **Spring Boot is generating traces:** Check Jaeger UI for service "react-springboot-app"
5. **Traces are connected:** A single trace should show both Kong and Spring Boot spans as parent-child
6. **Trace-log correlation:** Check that Spring Boot logs in Loki contain `trace_id` field matching Jaeger trace IDs
7. **Grafana Jaeger datasource:** Grafana Explore → Jaeger → search by service → traces appear
8. **Cross-pillar links:** In Grafana, clicking a trace span should offer "View logs" (→ Loki) and "View metrics" (→ Prometheus)

### Common Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| No traces in Jaeger UI | OTel agent not attached, wrong endpoint, firewall blocking 4317 | Check Spring Boot logs for OTel agent startup, verify endpoint, check `ufw status` |
| Kong traces and Spring traces are separate (not linked) | Propagation format mismatch | Ensure Kong uses `header_type: w3c` and OTel agent uses `tracecontext` propagator (default) |
| Traces appear but no spans for MySQL queries | OTel agent not instrumenting JDBC | Verify the JDBC driver is standard (not a custom wrapper). Check `-Dotel.instrumentation.jdbc.enabled=true` |
| `trace_id` not in logs | Logging framework not reading MDC | Add `%X{trace_id}` to logback pattern, or use JSON encoder |
| Jaeger shows "no storage backend configured" | Jaeger v2 config missing or wrong path | Verify `--config` flag points to correct YAML, check Jaeger container logs |
| Badger errors about corrupted data | Dirty shutdown, disk full | Stop Jaeger, delete `/data/badger/*`, restart. Data is lost but traces are reconstructed over time. |

---

## Current Status & Priorities

### Done
- [x] VM infrastructure provisioned (VMware Workstation Pro 17)
- [x] Ansible control node configured (SSH keys, inventory, ansible.cfg)
- [x] Ansible connectivity verified (ping all hosts)
- [x] Group variables defined (all.yml, monitoring.yml, application.yml, network.yml)
- [x] Role structure created

### In Progress — CURRENT FOCUS
- [ ] **Jaeger role**: Deploy Jaeger v2 all-in-one with Badger storage
- [ ] **OTel Java agent**: Attach to Spring Boot, verify trace generation
- [ ] **Kong OTel plugin**: Enable and verify trace propagation
- [ ] **Grafana Jaeger datasource**: Provision and verify cross-pillar links

### Next
- [ ] Prometheus role (scrape targets, alert rules)
- [ ] Loki role (server config, retention)
- [ ] Promtail role (log shipping from all VMs)
- [ ] Grafana role (dashboards, alerting, datasource provisioning)
- [ ] Integration testing (full request → trace → log → metric correlation)

### Future (post-demo)
- [ ] Drain3 anomaly detector
- [ ] LLM triage service + MCP servers
- [ ] Self-hosted LLM (Ollama)
- [ ] Grafana alert rules with webhook to triage service

---

## Design Decisions Log

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Metrics backend | Prometheus | Zabbix, VictoriaMetrics | Native Grafana integration, PromQL, pull-based simplicity |
| Log backend | Loki | Elasticsearch | 6x less storage, minimal ops, native Grafana, no JVM tuning |
| Trace backend | Jaeger v2 + Badger | Tempo, Zipkin, Elastic APM | CNCF standard, OTLP native, embedded storage for lab scale |
| Trace storage | Badger (embedded) | Elasticsearch, Cassandra | Zero operational overhead, sufficient for lab/demo scale |
| Visualization | Grafana (single pane) | Kibana, separate UIs | Unified view across all three pillars + alerting in one tool |
| Alerting | Grafana Alerting only | Alertmanager, Kibana alerts | Queries both PromQL and LogQL, webhook output to LLM triage. Alertmanager would be redundant routing brain. |
| Alert routing | Alerts → LLM first | Alerts → humans directly | LLM acts as triage layer, reduces alert fatigue, only real problems reach team |
| First-pass detection | Grafana thresholds + Drain3 | Elastic ML | Zero licensing cost. Grafana catches known failures, Drain3 catches unknown patterns. LLM validates both. |
| Trace propagation | W3C Trace Context | Zipkin B3, Jaeger native | Industry standard, supported by both Kong OTel plugin and OTel Java agent by default |
| Deployment | Docker Compose via Ansible | K8s, bare metal | Right complexity for 4-VM lab. K8s is future target. |
| Config management | Ansible | Terraform, manual | Infrastructure already exists (VMs created manually). Ansible manages config + deployment. Terraform for future IaC. |

---

## References

- [Jaeger v2 Documentation](https://www.jaegertracing.io/docs/latest/)
- [Jaeger v2 Configuration](https://www.jaegertracing.io/docs/latest/configuration/)
- [OpenTelemetry Java Agent](https://opentelemetry.io/docs/zero-code/java/agent/)
- [OTel Java Agent Configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/)
- [Kong OpenTelemetry Plugin](https://docs.konghq.com/hub/kong-inc/opentelemetry/)
- [Grafana Jaeger Datasource](https://grafana.com/docs/grafana/latest/datasources/jaeger/)
- [Badger (Dgraph)](https://github.com/dgraph-io/badger)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
