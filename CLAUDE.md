# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an Ansible-based infrastructure automation project that deploys a full observability stack across three VMs in an integration environment.

## Common Commands

```bash
# Run full playbook against all hosts
ansible-playbook playbooks/site.yml

# Run per-group
ansible-playbook playbooks/monitoring.yml
ansible-playbook playbooks/application.yml
ansible-playbook playbooks/network.yml

# Run only specific tags
ansible-playbook playbooks/site.yml --tags "monitoring"

# Dry run (check mode)
ansible-playbook playbooks/site.yml --check

# Test connectivity
ansible all -m ping

# Run ad-hoc command on a group
ansible monitoring -m shell -a "docker ps"
```

The default inventory (`inventory/production.yml`) and SSH key (`~/.ssh/ansible_key`) are pre-configured in `ansible.cfg`. Remote user is `deploy` with passwordless sudo.

## Infrastructure Layout

Three VMs, each with a dedicated role:

| Host | IP | Role |
|------|----|------|
| `monitoring-vm` | 192.168.127.10 | Observability stack |
| `application-vm` | 192.168.127.30 | App workloads |
| `network-vm` | 192.168.127.15 | Kong API Gateway |
| Ansible control | 192.168.127.20 | (not managed, firewall allowlist) |

## Architecture

Each VM runs ONE unified docker-compose file deployed to `/opt/stack/docker-compose.yml`. Templates are in `playbooks/templates/`.

### Monitoring VM (monitoring-vm)

Services: Prometheus (:9090), Loki (:3100), Jaeger (:16686 UI, :4327/:4328 OTLP), OTel Collector (:4317/:4318 OTLP, :8888 metrics), Grafana (:3000), node_exporter (:9100), cAdvisor (:8081)

Trace flow: Kong/Java agent -> OTel Collector (:4317) -> Jaeger (:4327)

### Application VM (application-vm)

Services: React frontend (:80), Spring Boot (:8080), MySQL (:3306), MySQL Exporter (:9104), Promtail (:9080), node_exporter (:9100), cAdvisor (:8081)

### Network VM (network-vm)

Services: Kong (:8000 proxy, :8001 admin), Promtail (:9080), node_exporter (:9100), cAdvisor (:8081)

## Project Structure

```
├── ansible.cfg
├── inventory/
│   ├── production.yml
│   └── group_vars/
│       ├── all.yml
│       ├── monitoring.yml
│       ├── network.yml
│       └── application.yml
├── playbooks/
│   ├── site.yml              # Master (imports all three)
│   ├── monitoring.yml
│   ├── application.yml
│   ├── network.yml
│   └── templates/
│       ├── monitoring-compose.yml.j2
│       ├── application-compose.yml.j2
│       └── network-compose.yml.j2
├── roles/
│   ├── common/               # Base packages, timezone, firewall
│   ├── docker/               # Docker CE installation
│   ├── node_exporter/        # System metrics (all VMs)
│   ├── cadvisor/             # Container metrics (all VMs)
│   ├── prometheus/           # Metrics server + alert rules
│   ├── loki/                 # Log aggregation
│   ├── jaeger/               # Distributed tracing (Badger storage)
│   ├── otel-collector/       # OTel Collector pipeline
│   ├── grafana/              # Dashboards + datasource provisioning
│   ├── promtail/             # Log shipper
│   ├── kong/                 # API Gateway (dbless)
│   ├── mysql/                # MySQL + exporter config
│   ├── spring_backend/       # Spring Boot + OTel Java agent
│   └── react_frontend/       # React frontend
└── requirements.yml
```

## Variable Hierarchy

```
inventory/group_vars/all.yml         # Shared: packages, ports, endpoints, Docker version, stack_dir
inventory/group_vars/monitoring.yml  # Grafana, Prometheus, Loki, Jaeger config, scrape targets
inventory/group_vars/application.yml # App ports, MySQL creds, OTel config, Promtail
inventory/group_vars/network.yml     # Kong ports/config/plugins, Promtail
inventory/production.yml             # Host IPs and per-host overrides
```

Key cross-group references: `loki_push_endpoint`, `jaeger_endpoint`, and `prometheus_host` in `all.yml` all point to `monitoring-vm` (192.168.127.10).
