# Observability Platform

Ansible-based observability stack deploying metrics, logs, and distributed tracing across 3 VMs in an integration environment. The monitored application is `mukundmadhav/react-springboot-mysql` — all instrumentation is injected externally via OpenTelemetry Java agent and Kong plugins.

---

## Infrastructure

| VM | Role | IP |
|---|---|---|
| VM1 | Monitoring (Prometheus, Loki, Jaeger, OTel Collector, Grafana) | 192.168.127.10 |
| VM2 | Network (Kong API Gateway) | 192.168.127.15 |
| VM3 | Application (Spring Boot + React, MySQL) | 192.168.127.30 |
| Control | Ansible control node | 192.168.127.20 |

- **OS:** Ubuntu Server 24.04 (all VMs)
- **Hypervisor:** VMware Workstation Pro 17
- **Network:** NAT subnet 192.168.127.0/24

---

## Quick Start

Deploy everything with `ansible-playbook playbooks/site.yml`, or target individual VMs with the per-group playbooks (`monitoring.yml`, `application.yml`, `network.yml`).

---

## Architecture Overview

### Observability Pillars

| Pillar | Collection | Storage | Visualization |
|---|---|---|---|
| **Metrics** | Prometheus scrapes all exporters (15s interval) | Prometheus TSDB (15d retention) | Grafana |
| **Logs** | Promtail (App + Network VMs) → Loki | Loki (7d retention) | Grafana |
| **Traces** | OTel Java Agent + Kong OTel Plugin → OTel Collector → Jaeger | Jaeger (Badger) | Grafana + Jaeger UI |

### Key Data Flows

- **Metrics:** Prometheus (.10) scrapes all exporters across 3 VMs (15s interval)
- **Traces:** OTel Java Agent (.30) and Kong OTel Plugin (.15) → OTel Collector (.10) → Jaeger
- **Logs:** Promtail (.30, .15) → Loki (.10:3100)
- **Traffic:** User → Kong (.15:8000) → Spring Boot (.30:80)

### Service Ports

#### VM1 — Monitoring

| Service | Port |
|---|---|
| Prometheus | :9090 |
| Loki | :3100 |
| Jaeger UI | :16686 |
| Jaeger OTLP (host) | :4327 (gRPC), :4328 (HTTP) |
| OTel Collector | :4317 (gRPC), :4318 (HTTP), :8888 (metrics) |
| Grafana | :3000 |
| node_exporter | :9100 |
| cAdvisor | :8081 |

#### VM2 — Network

| Service | Port |
|---|---|
| Kong Proxy | :8000 |
| Kong Admin + /metrics | :8001 |
| node_exporter | :9100 |
| cAdvisor | :8081 |

#### VM3 — Application

| Service | Port |
|---|---|
| Spring Boot + React | :80 (host) → :8080 (container) |
| MySQL | :3306 |
| MySQL Exporter | :9104 |
| Promtail | :9080 |
| node_exporter | :9100 |
| cAdvisor | :8081 |

---

## Project Structure

The project follows standard Ansible layout: `inventory/` (host IPs and group variables), `playbooks/` (site, monitoring, application, network playbooks + Jinja2 docker-compose templates), and `roles/` (15 roles covering common setup, Docker, all observability services, Kong, MySQL, and the application). A load test script and interactive architecture diagram are included at the root.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Metrics backend | Prometheus | Native Grafana integration, PromQL, pull-based |
| Log backend | Loki | Lightweight, no JVM, native Grafana |
| Trace backend | Jaeger v2 + Badger | CNCF standard, OTLP native, embedded storage |
| Visualization | Grafana | Unified view across all three pillars |
| API Gateway | Kong (dbless) | Declarative config, OTel + Prometheus plugins |
| Trace propagation | W3C Trace Context + B3 | Industry standard, Kong + OTel agent compatible |
| Deployment | Docker Compose via Ansible | Right complexity for 3-VM integration environment |

---

## Important Notes

- Jaeger v2 host ports are remapped (4327/4328) to avoid conflict with OTel Collector (4317/4318).
- Spring actuator metrics are scraped through Kong (`:8000/actuator/prometheus`), not directly.
- Kong OTel plugin is configured per-service (not global) with W3C inject and W3C+B3 extraction.
- Grafana datasources use Docker service names (`prometheus`, `loki`, `jaeger`), not localhost.
- `grafana_admin_password`, `mysql_password`, `mysql_root_password` are weak defaults — change for production.

---

## References

- [Jaeger Documentation](https://www.jaegertracing.io/docs/latest/)
- [OpenTelemetry Java Agent](https://opentelemetry.io/docs/zero-code/java/agent/)
- [Kong OpenTelemetry Plugin](https://docs.konghq.com/hub/kong-inc/opentelemetry/)
- [Grafana Datasources](https://grafana.com/docs/grafana/latest/datasources/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
