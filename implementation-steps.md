# Implementation Steps — Observability Platform Build Guide

> **Who this is for:** You are a DevOps intern (or anyone learning infrastructure automation). This document assumes you know basic Linux commands (`cd`, `ls`, `ssh`, `apt`) but may be **new to Ansible, Docker Compose, Prometheus, Loki, Jaeger, and Grafana**. Every step explains *what* we did, *where* the files live, *how* they work, and *why* we chose this approach.
>
> **Goal:** After reading this, you can rebuild the entire observability platform from scratch without any AI assistance.
>
> **Project:** AI-enhanced observability platform for CIRES Technologies (Tanger Med)
> **Date:** 2026-03-08

---

## Table of Contents

- [How to Read This Document](#how-to-read)
- [Architecture Overview](#architecture)
- [Step 0 — Prerequisites (Before You Touch Ansible)](#step-0)
- [Step 1 — Create the Master Playbook (site.yml)](#step-1)
- [Step 2 — Fix Variable Issues in group_vars](#step-2)
- [Step 3 — Build the Common Role (packages, firewall, node_exporter, cAdvisor)](#step-3)
- [Step 4 — Build the Docker Role](#step-4)
- [Step 5 — Build the Prometheus Role](#step-5)
- [Step 6 — Build the Loki Role](#step-6)
- [Step 7 — Build the Jaeger Role (Distributed Tracing)](#step-7)
- [Step 8 — Build the Grafana Role (Unified Dashboard)](#step-8)
- [Step 9 — Build the Promtail Role (Log Shipping)](#step-9)
- [Step 10 — Build the Application Role (React + Spring Boot + MySQL + OTel)](#step-10)
- [Step 11 — Build the Kong Role (API Gateway + Tracing)](#step-11)
- [Step 12 — Run the Playbook and Verify](#step-12)
- [Step 13 — Verification Checklist](#step-13)
- [Appendix A — Troubleshooting](#appendix-a)
- [Appendix B — File Map (every file and its purpose)](#appendix-b)
- [Appendix C — Future Enhancements](#appendix-c)

---

<a name="how-to-read"></a>
## How to Read This Document

Each step follows this pattern:

1. **What are we doing?** — Plain English explanation
2. **Why?** — The reasoning behind it
3. **Where?** — Exact file paths
4. **How?** — The actual code/config with line-by-line explanations
5. **Beginner Note** — Extra context if you're new to the tool

> **Tip:** If a concept is unfamiliar, don't skip it. Read the "Beginner Note" boxes — they are written specifically for you.

---

<a name="architecture"></a>
## Architecture Overview

Before building anything, understand what we're building and why:

```
                    ┌─────────────────────────────────────────────┐
                    │          VM1 — Monitoring (192.168.127.10)  │
                    │                                             │
 ┌──────────┐      │  ┌────────────┐  ┌──────┐  ┌────────┐      │
 │ Your     │      │  │ Prometheus │  │ Loki │  │ Jaeger │      │
 │ Browser  │─────►│  │  :9090     │  │:3100 │  │:16686  │      │
 │          │      │  └────────────┘  └──────┘  └────────┘      │
 └──────────┘      │  ┌──────────────────────────────────┐      │
                    │  │ Grafana :3000 (unified dashboard)│      │
                    │  │ Queries all three backends above │      │
                    │  └──────────────────────────────────┘      │
                    └─────────────────────────────────────────────┘
                           ▲ scrapes       ▲ push        ▲ OTLP
                           │ metrics       │ logs        │ traces
                    ┌──────┴───────┐ ┌─────┴────┐ ┌─────┴──────┐
                    │ node_exporter│ │ Promtail │ │ OTel Agent │
                    │ cAdvisor     │ │ (each VM)│ │ Kong OTel  │
                    │ (each VM)    │ │          │ │ plugin     │
                    └──────────────┘ └──────────┘ └────────────┘
```

**Three pillars of observability:**
- **Metrics** (numbers over time): "CPU is at 85%", "200 requests/sec" → Prometheus
- **Logs** (text events): "ERROR: database connection timeout at 14:32" → Loki
- **Traces** (request journeys): "This request took 450ms: 10ms in Kong, 400ms in Spring Boot, 40ms in MySQL" → Jaeger

**Why Grafana?** It's the single dashboard that queries all three backends. Instead of switching between Prometheus UI, Jaeger UI, and Loki, you use one tool.

---

<a name="step-0"></a>
## Step 0 — Prerequisites (Before You Touch Ansible)

**Status:** Already done. This section documents what was set up before the automation began.

### What you need:

1. **Four Ubuntu 24.04 VMs** (created in VMware Workstation Pro 17):

   | VM | IP | RAM | Purpose |
   |---|---|---|---|
   | monitoring-vm | 192.168.127.10 | 6GB+ | Prometheus, Loki, Jaeger, Grafana |
   | network-vm | 192.168.127.15 | 2GB | Kong API Gateway |
   | application-vm | 192.168.127.30 | 4GB | React + Spring Boot + MySQL |
   | Control node | 192.168.127.20 | 2GB | Where you run Ansible (this machine) |

2. **A `deploy` user on each managed VM** with:
   - Passwordless SSH from control node: `ssh-copy-id -i ~/.ssh/ansible_key deploy@192.168.127.10`
   - Passwordless sudo: add `deploy ALL=(ALL) NOPASSWD:ALL` to `/etc/sudoers`

3. **Ansible installed** on the control node:
   ```bash
   sudo apt update && sudo apt install -y ansible
   ```

4. **The project directory** with inventory and variables already defined (Steps 0.1–0.4 in README).

> **Beginner Note — What is Ansible?**
> Ansible is a tool that lets you configure multiple servers from one place. Instead of SSHing into each VM and running commands manually, you write YAML files describing what you want, and Ansible makes it happen on all VMs simultaneously. Key concepts:
> - **Inventory** (`inventory/int.yml`): Lists your servers and their IPs
> - **Playbook** (`site.yml`): Says "run these roles on these hosts"
> - **Role**: A reusable package of tasks, templates, and config for one service (e.g., "prometheus" role)
> - **Task**: A single action (e.g., "install this package", "copy this file")
> - **Template** (`.j2` files): Config files with variables that Ansible fills in (e.g., `{{ prometheus_port }}` becomes `9090`)
> - **Handler**: A task that only runs when notified (e.g., "restart prometheus" only runs if the config file changed)
> - **group_vars**: Variables that apply to a group of hosts (e.g., all hosts in the `monitoring` group get `grafana_port: 3000`)

### File: ansible.cfg

**Where:** `/root/monitoring-project/ansible.cfg`
**What it does:** Tells Ansible where to find inventory, which SSH key to use, and how to connect.

```ini
[defaults]
inventory = inventory/int.yml          # Where the server list is
private_key_file = ~/.ssh/ansible_key  # SSH key for connecting to VMs
remote_user = deploy                   # Which user to SSH as
host_key_checking = False              # Don't ask "are you sure?" on first SSH
forks = 3                              # Run on 3 hosts simultaneously
pipelining = True                      # Faster: reduces SSH round-trips
roles_path = roles                     # Where to find role directories
retry_files_enabled = True             # Save failed hosts for re-run

[privilege_escalation]
become = True                          # Use sudo on remote hosts
become_method = sudo                   # How to escalate privileges
become_ask_pass = False                # Don't prompt for sudo password
```

> **Beginner Note — `become: True`:** Most tasks need root access (installing packages, writing to /etc/). `become: True` means Ansible automatically adds `sudo` to every command. Since the `deploy` user has `NOPASSWD` sudo, it never asks for a password.

### Inventory: inventory/int.yml

**Where:** `/root/monitoring-project/inventory/int.yml`
**What it does:** Defines the three groups of servers and their connection details.

```yaml
all:
  children:
    monitoring:              # Group name — used in playbooks as "hosts: monitoring"
      hosts:
        monitoring-vm:       # Friendly name for this host
          ansible_host: 192.168.127.10   # Actual IP address
          ansible_user: deploy
    application:
      hosts:
        application-vm:
          ansible_host: 192.168.127.30
          ansible_user: deploy
          app_port: 8080     # Host-specific variable
    network:
      hosts:
        network-vm:
          ansible_host: 192.168.127.15
          ansible_user: deploy
  vars:                      # Variables that apply to ALL hosts
    ansible_python_interpreter: /usr/bin/python3
    ansible_ssh_private_key_file: ~/.ssh/ansible_key
    timezone: "Africa/Casablanca"
```

### Test connectivity:
```bash
ansible all -m ping
```
Expected output: all three hosts return `"pong"`.

---

<a name="step-1"></a>
## Step 1 — Create the Master Playbook (site.yml)

**What:** The master playbook that orchestrates everything. When you run `ansible-playbook site.yml`, this file tells Ansible: "First set up all VMs with common packages and Docker, then deploy the monitoring stack, then the app, then Kong."

**Where:** `/root/monitoring-project/site.yml`

**Why this order matters:**
1. `common` + `docker` run on ALL VMs first — because every service needs Docker installed
2. Monitoring stack (`prometheus`, `loki`, `jaeger`, `grafana`) runs second — because the app and Kong *send data to* these services, so they must be running first
3. Application stack runs third — Spring Boot sends traces to Jaeger and metrics to Prometheus
4. Network gateway runs last — Kong routes traffic to the application

```yaml
---
# Master playbook — deploys full observability stack
# Usage: ansible-playbook site.yml
# Limit to group: ansible-playbook site.yml --limit monitoring

- name: Common setup for all hosts       # Play 1: runs on all 3 VMs
  hosts: all
  roles:
    - common                              # Packages, firewall, node_exporter, cAdvisor
    - docker                              # Docker CE + Compose plugin
  tags: [common, docker]

- name: Deploy monitoring stack           # Play 2: runs only on monitoring-vm
  hosts: monitoring
  roles:
    - prometheus                          # Metrics backend
    - loki                                # Logs backend
    - jaeger                              # Traces backend
    - grafana                             # Unified dashboard
  tags: [monitoring]

- name: Deploy application stack          # Play 3: runs only on application-vm
  hosts: application
  roles:
    - app                                 # React + Spring Boot + MySQL + OTel agent
    - promtail                            # Ships app logs to Loki
  tags: [application]

- name: Deploy network gateway            # Play 4: runs only on network-vm
  hosts: network
  roles:
    - kong                                # API Gateway with OTel tracing
    - promtail                            # Ships Kong logs to Loki
  tags: [network]
```

> **Beginner Note — Tags:** The `tags` let you run only part of the playbook. For example:
> ```bash
> ansible-playbook site.yml --tags monitoring    # Only deploy monitoring stack
> ansible-playbook site.yml --limit application  # Only run on application-vm
> ```
> This is incredibly useful when debugging — you don't want to wait for ALL VMs when you're only fixing Prometheus.

---

<a name="step-2"></a>
## Step 2 — Fix Variable Issues in group_vars

**What:** We found and fixed several bugs in the variable files that were defined earlier.

**Why:** These variables are used by templates across all roles. Wrong values here = broken services everywhere.

### Fix 2a: Jaeger endpoint (all.yml)

**Where:** `inventory/group_vars/all.yml`
**Bug:** `jaeger_endpoint` pointed to `http://192.168.127.10:14268/api/traces` — this is the **old Jaeger v1** HTTP collector format.
**Fix:** Changed to `http://192.168.127.10:4317` — Jaeger v2 uses **OTLP on port 4317**.

```yaml
# BEFORE (wrong — Jaeger v1 format):
jaeger_endpoint: "http://192.168.127.10:14268/api/traces"

# AFTER (correct — Jaeger v2 OTLP):
jaeger_endpoint: "http://192.168.127.10:4317"
```

> **Beginner Note — Why does the port matter?**
> Jaeger v1 and v2 use completely different protocols. v1 had a custom HTTP endpoint at port 14268. v2 is built on OpenTelemetry and uses the OTLP standard protocol at port 4317 (gRPC) or 4318 (HTTP). If you use the wrong port, traces will silently fail — they'll be sent but nobody will be listening.

### Fix 2b: OTel exporter endpoint (application.yml)

**Where:** `inventory/group_vars/application.yml`
**Bug:** Same v1 endpoint issue as above, plus missing MySQL exporter variables.
**Fix:** Updated endpoint + added MySQL exporter config.

```yaml
# Changed:
otel_exporter_endpoint: "http://192.168.127.10:4317"

# Added:
mysql_exporter_port: 9104
mysql_exporter_version: "0.16.0"
```

### Fix 2c: Typo + missing scrape targets (monitoring.yml)

**Where:** `inventory/group_vars/monitoring.yml`
**Bugs:**
1. Typo: `app-spring-acutator` → `app-spring-actuator` (Prometheus won't scrape if the job name is wrong in dashboards/alerts)
2. Missing targets: Prometheus, Grafana, Loki, Jaeger, and MySQL exporter were not in the scrape list

**Fix:** Corrected typo and added 5 new scrape targets:

```yaml
  # Self-monitoring targets (added):
  - job: "prometheus"
    host: "192.168.127.10"
    port: "{{ prometheus_port }}"    # 9090
  - job: "grafana"
    host: "192.168.127.10"
    port: "{{ grafana_port }}"       # 3000
  - job: "loki"
    host: "192.168.127.10"
    port: "{{ loki_port }}"          # 3100
  - job: "jaeger"
    host: "192.168.127.10"
    port: "14269"                    # Jaeger admin/metrics port
  - job: "app-mysql"
    host: "192.168.127.30"
    port: "9104"                     # MySQL exporter
```

> **Beginner Note — Why self-monitor?** Prometheus should scrape its own metrics and the metrics of other monitoring tools (Grafana, Loki, Jaeger). This lets you answer questions like "Is Loki running out of memory?" or "How fast is Prometheus processing queries?" — which is essential when debugging the monitoring stack itself.

---

<a name="step-3"></a>
## Step 3 — Build the Common Role

**What:** The `common` role runs on ALL three VMs. It installs prerequisite packages, configures the timezone and firewall, and deploys two monitoring agents: **node_exporter** (host metrics) and **cAdvisor** (container metrics).

**Why these agents on every VM?**
- **node_exporter** exposes CPU, RAM, disk, and network stats as Prometheus metrics. Without it, you're blind to the host's health.
- **cAdvisor** exposes per-container metrics (CPU, memory, network per Docker container). Without it, you can't tell which container is eating resources.

**Where:** `roles/common/`

### File structure:
```
roles/common/
├── tasks/
│   ├── main.yml              # Entry point — Ansible always looks for tasks/main.yml
│   ├── node_exporter.yml     # Sub-tasks for node_exporter (imported by main.yml)
│   └── cadvisor.yml          # Sub-tasks for cAdvisor (imported by main.yml)
├── templates/
│   ├── node-exporter-compose.yml.j2    # Docker Compose for node_exporter
│   └── cadvisor-compose.yml.j2         # Docker Compose for cAdvisor
└── handlers/
    └── main.yml              # Restart handlers
```

### tasks/main.yml — Explained line by line:

```yaml
---
- name: Update apt cache                    # Refresh package index (like running apt update)
  apt:
    update_cache: yes
    cache_valid_time: 3600                   # Don't re-update if it was updated in the last hour
  tags: [packages]

- name: Install common packages              # Install tools every VM needs
  apt:
    name: "{{ common_packages }}"            # Reads the list from group_vars/all.yml
    state: present                           # Install if not present, don't upgrade
  tags: [packages]
```

> **Beginner Note — `{{ common_packages }}`:** This is a Jinja2 variable. Ansible replaces it with the value from `inventory/group_vars/all.yml`, which contains: `[curl, wget, vim, htop, net-tools, jq, unzip, ca-certificates, gnupg]`. These are standard sysadmin tools you'll need for debugging.

```yaml
- name: Set timezone
  timezone:
    name: "{{ timezone }}"                   # "Africa/Casablanca" from inventory/int.yml
  tags: [timezone]
```

```yaml
- name: Enable and configure UFW            # UFW = Uncomplicated Firewall
  when: firewall_enabled | default(false)    # Only if firewall_enabled is true in group_vars
  block:                                     # "block" groups multiple tasks under one condition
    - name: Allow SSH
      ufw:
        rule: allow
        port: "{{ ssh_port }}"               # 22
        proto: tcp

    - name: Allow traffic from Ansible control node
      ufw:
        rule: allow
        from_ip: "{{ ansible_control_ip }}"  # 192.168.127.20

    - name: Allow traffic within monitoring subnet
      ufw:
        rule: allow
        from_ip: 192.168.127.0/24           # All VMs can talk to each other

    - name: Enable UFW (default deny incoming)
      ufw:
        state: enabled
        default: deny
        direction: incoming                  # Block everything not explicitly allowed
  tags: [firewall]
```

> **Beginner Note — Why a firewall?** Even in a lab, it's good practice. UFW blocks all incoming traffic by default, then we punch holes for SSH (so Ansible can connect) and for the entire monitoring subnet (so services can talk to each other). In production, you'd be more specific about which ports to allow.

```yaml
- name: Deploy node_exporter                 # Import the sub-task file
  import_tasks: node_exporter.yml
  tags: [node_exporter]

- name: Deploy cAdvisor
  import_tasks: cadvisor.yml
  tags: [cadvisor]
```

### tasks/node_exporter.yml:

```yaml
---
- name: Create node_exporter directory
  file:
    path: /opt/node_exporter
    state: directory
    mode: "0755"

- name: Deploy node_exporter docker-compose
  template:
    src: node-exporter-compose.yml.j2        # Source: templates/ directory in this role
    dest: /opt/node_exporter/docker-compose.yml
    mode: "0644"
  notify: restart node_exporter              # If the file changes, trigger the handler

- name: Start node_exporter
  community.docker.docker_compose_v2:        # Ansible module that runs "docker compose up -d"
    project_src: /opt/node_exporter          # Directory containing docker-compose.yml
    state: present                           # Ensure containers are running
```

> **Beginner Note — `community.docker.docker_compose_v2`:** This is an Ansible module (a pre-built command) that manages Docker Compose projects. `state: present` means "start the containers if they're not running." `state: restarted` means "stop and re-start." It's equivalent to running `docker compose up -d` on the remote machine.

### templates/node-exporter-compose.yml.j2:

```yaml
services:
  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    restart: unless-stopped                  # Auto-restart on crash or reboot
    ports:
      - "{{ node_port }}:9100"               # Expose on host port 9100
    volumes:                                 # Mount host directories read-only
      - /proc:/host/proc:ro                  # Process info (CPU, memory per process)
      - /sys:/host/sys:ro                    # Kernel/hardware info
      - /:/rootfs:ro                         # Filesystem info (disk usage)
    command:                                 # Tell node_exporter where to find host data
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
```

> **Beginner Note — Why mount /proc, /sys, /?** node_exporter runs inside a Docker container, which is isolated from the host. To report the HOST's CPU/RAM/disk (not the container's), we mount the host's `/proc`, `/sys`, and `/` into the container as read-only volumes. The `--path.*` flags tell node_exporter "the host's /proc is at /host/proc inside this container."

### templates/cadvisor-compose.yml.j2:

```yaml
services:
  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    container_name: cadvisor
    restart: unless-stopped
    ports:
      - "{{ cadvisor_port }}:8080"           # cAdvisor listens on 8080 internally
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro                 # Docker socket access
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro  # Docker container data
      - /dev/disk/:/dev/disk:ro              # Disk device info
    privileged: true                         # Needs privileged mode for kernel stats
    devices:
      - /dev/kmsg                            # Kernel message buffer
```

### handlers/main.yml:

```yaml
---
- name: restart node_exporter
  community.docker.docker_compose_v2:
    project_src: /opt/node_exporter
    state: restarted

- name: restart cadvisor
  community.docker.docker_compose_v2:
    project_src: /opt/cadvisor
    state: restarted
```

> **Beginner Note — What is a handler?** A handler is a task that only runs when "notified." In `node_exporter.yml`, the template task has `notify: restart node_exporter`. This means: "If the docker-compose file actually changes, restart the container." If nothing changes, the handler doesn't run. This prevents unnecessary restarts.

---

<a name="step-4"></a>
## Step 4 — Build the Docker Role

**What:** Installs Docker CE (Community Edition) and the Docker Compose plugin on every VM. Every service in this project runs as a Docker container, so this is foundational.

**Where:** `roles/docker/`

**Why Docker?** Instead of installing Prometheus, Loki, Jaeger, etc. directly on each VM (which requires managing dependencies, versions, conflicts), we run each service in an isolated container. Docker Compose lets us define multi-container setups in a single YAML file.

### tasks/main.yml — Explained:

```yaml
---
- name: Remove old Docker packages           # Clean up any pre-installed Docker versions
  apt:
    name: [docker, docker-engine, docker.io, containerd, runc]
    state: absent

- name: Install Docker prerequisites          # Tools needed to add Docker's repo
  apt:
    name: [ca-certificates, curl, gnupg, lsb-release]
    state: present
    update_cache: yes

- name: Create Docker keyring directory       # Where apt stores GPG keys
  file:
    path: /etc/apt/keyrings
    state: directory
    mode: "0755"

- name: Add Docker GPG key                    # Verify packages are from Docker, not tampered
  shell: |
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
  args:
    creates: /etc/apt/keyrings/docker.gpg    # Skip if already done (idempotent)

- name: Add Docker apt repository             # Tell apt where to find Docker packages
  shell: |
    echo "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
  args:
    creates: /etc/apt/sources.list.d/docker.list

- name: Update apt cache after adding Docker repo
  apt:
    update_cache: yes

- name: Install Docker CE and plugins
  apt:
    name:
      - docker-ce                             # Docker engine
      - docker-ce-cli                         # docker command
      - containerd.io                         # Container runtime
      - docker-buildx-plugin                  # Multi-platform builds
      - docker-compose-plugin                 # "docker compose" command (v2)
    state: present

- name: Ensure Docker service is started and enabled
  systemd:
    name: docker
    state: started                            # Start now
    enabled: yes                              # Start on boot

- name: Add deploy user to docker group       # So deploy can run docker without sudo
  user:
    name: "{{ ansible_user }}"                # "deploy"
    groups: docker
    append: yes                               # Don't remove from other groups
```

> **Beginner Note — Why `docker-compose-plugin` and not standalone `docker-compose`?**
> The old `docker-compose` (v1) was a separate Python program. The new `docker compose` (v2, no hyphen) is a Docker plugin — faster, better maintained, and installed via `docker-compose-plugin`. When you see `docker compose up` (space, not hyphen), that's v2. The Ansible module `community.docker.docker_compose_v2` uses this v2 plugin.

---

<a name="step-5"></a>
## Step 5 — Build the Prometheus Role

**What:** Deploys Prometheus — the metrics collection engine. Prometheus **pulls** (scrapes) metrics from all services every 15 seconds and stores them in a time-series database (TSDB).

**Where:** `roles/prometheus/`

**Why Prometheus?** It's the industry standard for metrics. It uses a pull model (Prometheus reaches out to each service and says "give me your metrics"), which means monitored services don't need to know where Prometheus is. PromQL (its query language) is powerful and well-documented.

### How Prometheus works (conceptual):

```
Every 15 seconds:
  Prometheus → HTTP GET http://192.168.127.30:9100/metrics → node_exporter responds with text:
    node_cpu_seconds_total{cpu="0",mode="idle"} 123456.78
    node_memory_MemAvailable_bytes 4294967296
    ...
  Prometheus stores these values with timestamps in its TSDB.
  Grafana queries: "Show me node_cpu_seconds_total for the last hour" → Prometheus returns data → Grafana draws a graph.
```

### Key files:

#### defaults/main.yml:
```yaml
prometheus_version: "latest"
prometheus_config_dir: /etc/prometheus        # Where config lives on the VM
prometheus_data_dir: /var/lib/prometheus       # Where time-series data is stored
```

> **Beginner Note — defaults vs group_vars:** `defaults/main.yml` in a role provides fallback values. `group_vars/monitoring.yml` provides group-specific values. If both define the same variable, group_vars wins. We put "stable, rarely-changed" values in defaults and "environment-specific" values in group_vars.

#### templates/prometheus.yml.j2 — The scrape configuration:

```yaml
global:
  scrape_interval: {{ prometheus_scrape_interval }}    # 15s — how often to pull metrics
  evaluation_interval: {{ prometheus_scrape_interval }} # 15s — how often to evaluate alert rules

scrape_configs:
{% for target in prometheus_targets %}                  # Loop over all targets from monitoring.yml
  - job_name: '{{ target.job }}'
{% if target.job == 'app-spring-actuator' %}
    metrics_path: '/actuator/prometheus'                # Spring Boot exposes metrics here, not /metrics
{% elif target.job == 'net-kong' %}
    metrics_path: '/metrics'                           # Kong exposes on /metrics at its admin port
{% endif %}
    static_configs:
      - targets: ['{{ target.host }}:{{ target.port }}']
{% endfor %}
```

> **Beginner Note — The `{% for %}` loop:** This is Jinja2 templating. Ansible reads `prometheus_targets` from `monitoring.yml` (a list of jobs with host and port), and the `{% for %}` loop generates one `scrape_config` entry for each target. So instead of writing 13 nearly-identical blocks by hand, we write the pattern once and loop.

> **Beginner Note — `metrics_path`:** Most services expose metrics at `/metrics` (the default). But Spring Boot uses `/actuator/prometheus`. If you don't set `metrics_path`, Prometheus will try `/metrics` and get a 404, and that target will show as "DOWN" in the Prometheus UI.

#### templates/docker-compose.yml.j2:

```yaml
services:
  prometheus:
    image: prom/prometheus:{{ prometheus_version }}
    container_name: prometheus
    restart: unless-stopped
    ports:
      - "{{ prometheus_port }}:9090"
    volumes:
      - {{ prometheus_config_dir }}/prometheus.yml:/etc/prometheus/prometheus.yml:ro  # Config
      - {{ prometheus_data_dir }}:/prometheus          # Data persistence
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time={{ prometheus_retention_days }}d'   # Keep 15 days of data
      - '--web.enable-lifecycle'              # Allow config reload via HTTP POST
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9090/-/ready"]
      interval: 10s
      timeout: 5s
      retries: 3
```

> **Beginner Note — `--web.enable-lifecycle`:** This flag lets you reload Prometheus config without restarting: `curl -X POST http://localhost:9090/-/reload`. Very useful when adding new scrape targets — no downtime needed.

---

<a name="step-6"></a>
## Step 6 — Build the Loki Role

**What:** Deploys Loki — the log aggregation engine. Unlike Prometheus (which pulls), Loki **receives pushes** from Promtail agents on each VM. It stores logs efficiently by indexing only labels (like `{job="spring-boot", host="application-vm"}`), not the full log text.

**Where:** `roles/loki/`

**Why Loki (not Elasticsearch)?** Loki uses ~6x less storage than Elasticsearch because it doesn't full-text index every log line. For a lab environment, this means less disk, less RAM, less complexity. Elasticsearch would need 2+ GB heap per node and careful JVM tuning.

### How Loki works (conceptual):

```
Promtail on application-vm reads /var/log/app/*.log
  → Each line gets labels: {job="spring-boot", host="application-vm"}
  → Pushed via HTTP POST to http://192.168.127.10:3100/loki/api/v1/push
  → Loki stores the log line in compressed chunks on disk
  → Loki indexes the labels (NOT the log content)
  → Grafana queries: {job="spring-boot"} |= "ERROR" → Loki returns matching logs
```

### templates/loki-config.yml.j2 — Key sections explained:

```yaml
auth_enabled: false                    # No multi-tenancy — single tenant mode

server:
  http_listen_port: 3100               # Loki API port

common:
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory                  # Single-node: no need for external KV store
  replication_factor: 1                # Single-node: no replication
  path_prefix: /loki                   # Base directory for all Loki data

schema_config:
  configs:
    - from: "2024-01-01"               # Schema version applies from this date
      store: tsdb                      # Use TSDB index (newer, faster than BoltDB)
      object_store: filesystem         # Store chunks on local disk
      schema: v13                      # Latest schema version
      index:
        prefix: index_
        period: 24h                    # New index table every 24 hours

storage_config:
  filesystem:
    directory: /loki/chunks            # Where compressed log data lives
  tsdb_shipper:
    active_index_directory: /loki/tsdb-index
    cache_location: /loki/tsdb-cache

limits_config:
  retention_period: {{ loki_retention_days * 24 }}h   # 7 days = 168h
  reject_old_samples: true             # Don't accept logs older than 7 days
  reject_old_samples_max_age: 168h
  ingestion_rate_mb: 16                # Max 16 MB/s log ingestion
  ingestion_burst_size_mb: 32          # Allow bursts up to 32 MB

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m             # Compact index files every 10 minutes
  retention_enabled: true              # Actually delete old logs (not just mark them)
  retention_delete_delay: 2h           # Wait 2h before deleting (safety margin)
  delete_request_store: filesystem
```

> **Beginner Note — retention_period:** `{{ loki_retention_days * 24 }}h` is Jinja2 math. `loki_retention_days` is `7` (from monitoring.yml), so this evaluates to `168h` (7 days). Logs older than 7 days are deleted by the compactor. This keeps disk usage bounded.

---

<a name="step-7"></a>
## Step 7 — Build the Jaeger Role (Distributed Tracing)

**What:** Deploys Jaeger v2 — the distributed tracing backend. It receives trace spans via OTLP (OpenTelemetry Protocol), stores them in Badger (an embedded key-value database), and provides a query API + web UI.

**Where:** `roles/jaeger/`

**Why Jaeger v2 specifically?**
- v2 is a complete rewrite built ON TOP of the OpenTelemetry Collector
- It natively speaks OTLP — no translation needed
- Badger is embedded — no separate database to manage
- For a lab: perfect. Zero operational overhead.

### How distributed tracing works (conceptual):

```
1. User hits Kong (.15:8000/api/orders)
2. Kong OTel plugin creates ROOT SPAN:
   {trace_id: "abc123", span_id: "span1", service: "kong-gateway", duration: 12ms}
   Kong adds header: traceparent: 00-abc123-span1-01
3. Kong forwards to Spring Boot (.30:8080) WITH the traceparent header
4. OTel Java agent on Spring Boot reads traceparent, creates CHILD SPAN:
   {trace_id: "abc123", span_id: "span2", parent: "span1", service: "react-springboot-app", duration: 10ms}
5. Spring Boot queries MySQL → OTel agent creates CHILD SPAN:
   {trace_id: "abc123", span_id: "span3", parent: "span2", operation: "SELECT * FROM orders", duration: 3ms}
6. All spans are sent via OTLP to Jaeger (.10:4317)
7. Jaeger groups all spans by trace_id="abc123" → complete picture of the request
```

### Key concept — Why `header_type: w3c` matters everywhere:

The `traceparent` header format must match between Kong and the OTel Java agent. Both must use W3C Trace Context format. If Kong uses a different format (like Zipkin B3), the Spring Boot agent won't recognize it, and you'll get TWO separate traces instead of one connected trace.

### templates/jaeger-config.yaml.j2:

```yaml
service:
  extensions: [jaeger_storage, jaeger_query]   # Enable storage + query API
  pipelines:
    traces:
      receivers: [otlp]                        # Accept traces via OTLP
      processors: [batch]                      # Batch spans before writing
      exporters: [jaeger_storage_exporter]     # Write to Badger

extensions:
  jaeger_storage:
    backends:
      badger_main:
        badger:
          directories:
            keys: /data/badger/keys            # LSM index (small, fast)
            values: /data/badger/values        # Actual span data (larger)
          ephemeral: false                     # Persist across restarts
          maintenance_interval: {{ jaeger_maintenance_interval }}   # 5m — garbage collection
          span_store_ttl: {{ jaeger_span_ttl }}                    # 168h — keep 7 days

  jaeger_query:
    storage:
      traces: badger_main                      # Query API reads from Badger

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:{{ jaeger_otlp_grpc_port }}"   # 4317 — main ingestion port
      http:
        endpoint: "0.0.0.0:{{ jaeger_otlp_http_port }}"   # 4318 — alternative

processors:
  batch:
    send_batch_size: {{ jaeger_batch_size }}    # 10000 — write in batches of 10k spans
    timeout: {{ jaeger_batch_timeout }}         # 5s — or every 5 seconds, whichever comes first

exporters:
  jaeger_storage_exporter:
    trace_storage: badger_main                 # Write batched spans to Badger
```

> **Beginner Note — What is Badger?**
> Badger is an embedded key-value database (like SQLite for key-value data). "Embedded" means it runs INSIDE the Jaeger process — no separate database server needed. It stores data in two directories:
> - `keys/` — The index (think: "table of contents"). Small, fast to search.
> - `values/` — The actual span data. Larger, grows over time.
> The `maintenance_interval` runs garbage collection to reclaim space from deleted spans. If you notice disk growing, check this value and `span_store_ttl`.

### templates/docker-compose.yml.j2:

```yaml
services:
  jaeger:
    image: jaegertracing/jaeger:{{ jaeger_version }}   # "jaegertracing/jaeger:2"
    container_name: jaeger
    restart: unless-stopped
    ports:
      - "{{ jaeger_ui_port }}:16686"       # Web UI — open in browser
      - "{{ jaeger_otlp_grpc_port }}:4317" # OTLP gRPC — where agents send traces
      - "{{ jaeger_otlp_http_port }}:4318" # OTLP HTTP — alternative
      - "{{ jaeger_admin_port }}:14269"    # Admin — health check + /metrics
    volumes:
      - {{ jaeger_config_dir }}/config.yaml:/etc/jaeger/config.yaml:ro
      - {{ jaeger_config_dir }}/ui-config.json:/etc/jaeger/ui-config.json:ro
      - {{ jaeger_data_dir }}:/data/badger  # Persistent span storage
    command: ["--config", "/etc/jaeger/config.yaml"]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:14269/"]
      interval: 10s
      timeout: 5s
      retries: 3
```

---

<a name="step-8"></a>
## Step 8 — Build the Grafana Role (Unified Dashboard)

**What:** Deploys Grafana — the visualization layer that connects to Prometheus (metrics), Loki (logs), and Jaeger (traces). One dashboard to see everything.

**Where:** `roles/grafana/`

**Why Grafana?** Instead of using 3 separate UIs (Prometheus UI, Jaeger UI, Loki doesn't even have a UI), Grafana provides one place to:
- Build dashboards with graphs (Prometheus data)
- Search logs (Loki data)
- Explore traces (Jaeger data)
- **Click from a trace span → jump to related logs in Loki** (cross-pillar correlation)
- Set up alerts that fire on metrics OR log patterns

### Key design decision — Auto-provisioned datasources:

Instead of manually adding datasources in the Grafana UI after deployment, we **provision them automatically** via a YAML file. This means every fresh deployment gets the same datasources configured — no manual steps.

### templates/datasources.yml.j2 — This is the magic file:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy                        # Grafana backend proxies requests to Prometheus
    url: http://localhost:{{ prometheus_port }}   # Same VM — use localhost
    isDefault: true                      # Default datasource for new panels
    uid: prometheus                      # Stable ID for cross-references

  - name: Loki
    type: loki
    access: proxy
    url: http://localhost:{{ loki_port }}
    uid: loki
    jsonData:
      derivedFields:                     # IMPORTANT: trace-log correlation
        - datasourceUid: jaeger          # When you find a trace_id in a log line...
          matcherRegex: "trace_id=(\\w+)" # ...extract it with this regex...
          name: TraceID
          url: "$${__value.raw}"          # ...and link to that trace in Jaeger

  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://localhost:{{ jaeger_port_ui }}
    uid: jaeger
    jsonData:
      tracesToMetrics:                   # Click a trace → see related metrics
        datasourceUid: prometheus
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        tags:
          - key: service.name
            value: service
      tracesToLogs:                      # Click a trace → see related logs
        datasourceUid: loki
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        filterByTraceID: true
        filterBySpanID: false
        tags:
          - key: service.name
            value: service
      nodeGraph:
        enabled: true                    # Service dependency graph visualization
```

> **Beginner Note — Cross-pillar correlation:** This is the real power of a unified observability platform:
> 1. You see a spike in error rate on a Grafana dashboard (metrics from Prometheus)
> 2. You click to see the logs around that time (logs from Loki)
> 3. You see a log line with `trace_id=abc123`
> 4. You click the trace ID → Grafana opens the full trace in Jaeger
> 5. You see exactly which service/query was slow
>
> The `derivedFields` in the Loki datasource and `tracesToLogs`/`tracesToMetrics` in the Jaeger datasource make this possible. Without them, you'd have to manually copy-paste trace IDs between UIs.

### templates/docker-compose.yml.j2:

```yaml
services:
  grafana:
    image: grafana/grafana:{{ grafana_version }}
    container_name: grafana
    restart: unless-stopped
    ports:
      - "{{ grafana_port }}:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: "{{ grafana_admin_password }}"   # "admin" — CHANGE IN PRODUCTION
      GF_USERS_ALLOW_SIGN_UP: "false"    # Disable self-registration
    volumes:
      - {{ grafana_data_dir }}:/var/lib/grafana
      - {{ grafana_provisioning_dir }}:/etc/grafana/provisioning:ro  # Auto-provision datasources
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 3
```

> **Beginner Note — UID 472:** The Grafana container runs as user 472 (the `grafana` user inside the container). The `tasks/main.yml` creates directories with `owner: "472"` so Grafana can write to them. If you use `owner: root`, Grafana will crash with "permission denied" errors.

---

<a name="step-9"></a>
## Step 9 — Build the Promtail Role (Log Shipping)

**What:** Deploys Promtail — a lightweight agent that reads log files on each VM and pushes them to Loki. Runs on application-vm and network-vm (and optionally monitoring-vm).

**Where:** `roles/promtail/`

**Why Promtail?** Loki can't reach into your VMs and read log files — something needs to push logs to it. Promtail is built specifically for Loki: lightweight, supports label extraction, and handles log rotation automatically.

### Key design: One role, different behavior per VM

The Promtail config is **different on each VM** because each VM has different logs:
- application-vm: `/var/log/app/*.log` (Spring Boot logs)
- network-vm: `/var/log/kong/*.log` (Kong access logs)
- monitoring-vm: `/var/log/*.log` (monitoring service logs)

We handle this with **Jinja2 conditionals** in the template:

### templates/promtail-config.yml.j2:

```yaml
server:
  http_listen_port: {{ promtail_http_port }}   # 9080 — Promtail's own status endpoint
  grpc_listen_port: 0                          # Disable gRPC (not needed)

positions:
  filename: /tmp/positions.yaml                # Tracks where Promtail left off in each file

clients:
  - url: {{ loki_push_endpoint }}              # http://192.168.127.10:3100/loki/api/v1/push

scrape_configs:
  - job_name: system                           # Every VM ships syslog
    static_configs:
      - targets: [localhost]
        labels:
          job: syslog
          host: {{ inventory_hostname }}        # "application-vm", "network-vm", etc.
          __path__: /var/log/syslog

{% if 'application' in group_names %}          # ONLY on application-vm:
  - job_name: app-logs
    static_configs:
      - targets: [localhost]
        labels:
          job: app
          host: {{ inventory_hostname }}
          __path__: /var/log/app/*.log

  - job_name: spring-boot
    static_configs:
      - targets: [localhost]
        labels:
          job: spring-boot
          host: {{ inventory_hostname }}
          __path__: /var/log/app/spring-boot.log
    pipeline_stages:
      - regex:
          expression: 'trace_id=(?P<trace_id>[a-f0-9]+)'   # Extract trace_id from log lines
      - labels:
          trace_id:                             # Add trace_id as a Loki label
{% endif %}

{% if 'network' in group_names %}              # ONLY on network-vm:
  - job_name: kong-logs
    static_configs:
      - targets: [localhost]
        labels:
          job: kong
          host: {{ inventory_hostname }}
          __path__: /var/log/kong/*.log
{% endif %}
```

> **Beginner Note — `group_names`:** This is a built-in Ansible variable. It contains the list of groups the current host belongs to. `application-vm` is in the `application` group, so `'application' in group_names` is `true` only on that VM. This is how one template produces different configs per host.

> **Beginner Note — pipeline_stages + trace_id extraction:** The `regex` stage extracts `trace_id` from log lines like `2024-03-08 14:32:01 INFO ... trace_id=abc123def456`. The `labels` stage adds `trace_id=abc123def456` as a Loki label. This lets Grafana's "derived fields" feature link logs to traces in Jaeger. Without this, you'd have to grep logs manually.

---

<a name="step-10"></a>
## Step 10 — Build the Application Role

**What:** Deploys the actual application being monitored: React frontend + Spring Boot REST API + MySQL database. Also attaches the OpenTelemetry Java agent to Spring Boot (for automatic trace generation) and deploys a MySQL exporter (for database metrics).

**Where:** `roles/app/`

**Why this is the most complex role:**
- 4 containers (MySQL, Spring Boot, React, MySQL Exporter) with dependencies between them
- OpenTelemetry Java agent requires specific environment variables
- MySQL needs an init script to grant monitoring permissions
- Spring Boot must wait for MySQL to be healthy before starting

### tasks/main.yml:

```yaml
---
- name: Create application directories
  file:
    path: "{{ item }}"
    state: directory
    mode: "0755"
  loop:
    - "{{ app_config_dir }}"       # /opt/app — Docker Compose + configs
    - "{{ otel_dir }}"             # /opt/otel — OTel Java agent JAR
    - "{{ app_log_dir }}"          # /var/log/app — Application logs

- name: Download OpenTelemetry Java agent
  get_url:
    url: "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v{{ otel_agent_version }}/opentelemetry-javaagent.jar"
    dest: "{{ otel_agent_jar }}"   # /opt/otel/opentelemetry-javaagent.jar
    mode: "0644"
```

> **Beginner Note — What does the OTel Java agent do?** It's a JAR file that you attach to any Java application (via `JAVA_TOOL_OPTIONS="-javaagent:/path/to/agent.jar"`). It uses bytecode manipulation to AUTOMATICALLY instrument:
> - Every HTTP request entering Spring MVC (creates a span)
> - Every JDBC query to MySQL (creates a child span)
> - Every outgoing HTTP call (propagates trace context)
> - Logging (injects trace_id into SLF4J MDC)
>
> You don't change a single line of application code. The agent does everything at JVM startup.

### templates/docker-compose.yml.j2 — Spring Boot with OTel agent:

```yaml
  spring-boot:
    image: mukundmadhav/spring-backend:latest
    container_name: spring-boot
    restart: unless-stopped
    ports:
      - "{{ app_backend_port }}:8080"
    environment:
      # Database connection
      SPRING_PROFILES_ACTIVE: "{{ spring_profile }}"           # "int"
      SPRING_DATASOURCE_URL: "jdbc:mysql://mysql:3306/{{ mysql_database }}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
      SPRING_DATASOURCE_USERNAME: "{{ mysql_user }}"
      SPRING_DATASOURCE_PASSWORD: "{{ mysql_password }}"

      # OpenTelemetry Java agent — THIS IS THE KEY PART:
      JAVA_TOOL_OPTIONS: "-javaagent:{{ otel_agent_jar }}"     # Attach the agent to the JVM
      OTEL_SERVICE_NAME: "{{ otel_service_name }}"             # "react-springboot-app" — shown in Jaeger
      OTEL_EXPORTER_OTLP_ENDPOINT: "{{ otel_exporter_endpoint }}"  # http://192.168.127.10:4317
      OTEL_EXPORTER_OTLP_PROTOCOL: "grpc"                     # Use gRPC (faster than HTTP)
      OTEL_TRACES_EXPORTER: "otlp"                             # Export traces via OTLP
      OTEL_METRICS_EXPORTER: "none"                            # Prometheus handles metrics
      OTEL_LOGS_EXPORTER: "none"                               # Promtail/Loki handles logs
      OTEL_PROPAGATORS: "tracecontext,baggage"                 # W3C Trace Context format

    volumes:
      - {{ otel_dir }}:{{ otel_dir }}:ro       # Mount OTel agent JAR into container
      - {{ app_log_dir }}:/var/log/app         # Mount log directory

    depends_on:
      mysql:
        condition: service_healthy             # Wait for MySQL to be ready
```

> **Beginner Note — `OTEL_METRICS_EXPORTER: "none"` and `OTEL_LOGS_EXPORTER: "none"`:**
> The OTel agent can export metrics and logs too, but we already have dedicated tools for those (Prometheus for metrics, Promtail/Loki for logs). Sending metrics through two paths would cause duplicates. So we tell the OTel agent: "Only handle traces. Leave metrics and logs to the specialist tools."

### templates/init.sql.j2 — MySQL init script:

```sql
-- Grant monitoring permissions for MySQL exporter
GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO '{{ mysql_user }}'@'%';
FLUSH PRIVILEGES;
```

> **Beginner Note:** The MySQL exporter needs `PROCESS` (to see running queries), `REPLICATION CLIENT` (to check replication status), and `SELECT` (to read performance metrics). Without these grants, the exporter will report errors and incomplete metrics.

---

<a name="step-11"></a>
## Step 11 — Build the Kong Role (API Gateway)

**What:** Deploys Kong Gateway in dbless (declarative) mode. Kong sits in front of the application, routing requests from users to the backend. It also generates distributed traces (root spans) and exposes Prometheus metrics.

**Where:** `roles/kong/`

**Why Kong?**
- API Gateway: rate limiting, authentication, routing — all in one place
- Plugin ecosystem: prometheus (metrics), opentelemetry (traces), http-log (logs), correlation-id (request tracking)
- Dbless mode: config is a YAML file, no database needed. Perfect for automation.

### templates/kong.yml.j2 — Declarative config:

```yaml
_format_version: "3.0"

services:
  - name: app-backend                         # Route /api requests to Spring Boot
    url: http://{{ app_backend_host }}:{{ app_backend_port }}   # http://192.168.127.30:8080
    routes:
      - name: api-route
        paths: [/api]
        strip_path: false                     # Forward /api/orders as-is (don't remove /api)
      - name: actuator-route
        paths: [/actuator]
        strip_path: false                     # Also expose Spring Boot actuator through Kong

  - name: app-frontend
    url: http://{{ app_backend_host }}:80      # React frontend
    routes:
      - name: frontend-route
        paths: [/]
        strip_path: false

plugins:
  - name: prometheus                          # Expose request metrics at :8001/metrics
    config:
      status_code_metrics: true
      latency_metrics: true
      bandwidth_metrics: true

  - name: correlation-id                      # Add unique request ID to every request
    config:
      header_name: X-Correlation-ID
      generator: uuid#counter
      echo_downstream: true                   # Include in response headers too

  - name: http-log                            # HTTP access logging
    config:
      http_endpoint: "{{ loki_push_endpoint }}"
      method: POST

  - name: opentelemetry                       # THE TRACING PLUGIN
    config:
      endpoint: "{{ jaeger_endpoint }}"       # http://192.168.127.10:4317
      resource_attributes:
        service.name: "kong-gateway"          # Service name shown in Jaeger
      header_type: w3c                        # MUST match OTel Java agent propagator
```

> **Beginner Note — `header_type: w3c` is CRITICAL:** This tells Kong to use the W3C Trace Context format for the `traceparent` header. The OTel Java agent on Spring Boot also uses W3C by default (`OTEL_PROPAGATORS: "tracecontext,baggage"`). If these don't match:
> - Kong creates a trace with ID "abc123"
> - Kong sends a header Spring Boot can't read
> - Spring Boot creates a NEW trace with ID "xyz789"
> - You see two disconnected traces instead of one
> This is the #1 cause of "my traces don't link together" problems.

### templates/docker-compose.yml.j2:

```yaml
services:
  kong:
    image: kong:{{ kong_version }}             # kong:3.9
    container_name: kong
    restart: unless-stopped
    ports:
      - "{{ kong_proxy_port }}:8000"          # Proxy — where users send requests
      - "{{ kong_admin_port }}:8001"          # Admin API + /metrics for Prometheus
    environment:
      KONG_DATABASE: "off"                    # Dbless mode — no PostgreSQL needed
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      KONG_PLUGINS: "bundled,opentelemetry"   # Enable OTel plugin (not bundled by default)
      KONG_TRACING_INSTRUMENTATIONS: all      # Trace all operations
      KONG_TRACING_SAMPLING_RATE: 1.0         # Trace 100% of requests (1.0 = all)
    volumes:
      - {{ kong_config_file }}:/etc/kong/kong.yml:ro
    healthcheck:
      test: ["CMD", "kong", "health"]
      interval: 10s
      timeout: 5s
      retries: 5
```

> **Beginner Note — `KONG_TRACING_SAMPLING_RATE: 1.0`:** In production, you'd set this to something like `0.01` (trace 1% of requests) to reduce overhead. For a lab/demo, `1.0` traces everything so you can always see full traces in Jaeger.

---

<a name="step-12"></a>
## Step 12 — Run the Playbook and Verify

### 12.1 — Dry run first (check mode)

Always do a dry run before applying changes:

```bash
ansible-playbook site.yml --check
```

This shows what Ansible WOULD do without actually doing it. Look for errors (red text).

> **Beginner Note:** Check mode is like a "preview." Some tasks will show "skipped" because they depend on things that check mode can't create (like Docker containers). That's normal. You're looking for YAML syntax errors or missing variables, which show as red failures.

### 12.2 — Run for real

```bash
# Full deployment — all VMs, all roles:
ansible-playbook site.yml

# Or deploy in stages (recommended for first time):
ansible-playbook site.yml --limit monitoring   # Step 1: monitoring stack
ansible-playbook site.yml --limit application  # Step 2: app stack
ansible-playbook site.yml --limit network      # Step 3: Kong gateway
```

> **Beginner Note — Why deploy in stages?** If something fails on the monitoring VM, you want to fix it before deploying the app (which tries to send data to the monitoring VM). Deploying in stages gives you a chance to verify each layer.

### 12.3 — Watch the output

Ansible shows each task with a color:
- **Green (ok):** Task succeeded, no changes needed
- **Yellow (changed):** Task succeeded and made a change
- **Red (failed):** Task failed — read the error message
- **Blue (skipping):** Task was skipped (condition not met)

---

<a name="step-13"></a>
## Step 13 — Verification Checklist

After deployment, verify each service is running:

### 13.1 — Check containers on each VM

```bash
# Monitoring VM:
ansible monitoring -m shell -a "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# Expected: prometheus, loki, jaeger, grafana, node-exporter, cadvisor

# Application VM:
ansible application -m shell -a "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# Expected: spring-boot, react-frontend, app-mysql, mysql-exporter, node-exporter, cadvisor, promtail

# Network VM:
ansible network -m shell -a "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# Expected: kong, node-exporter, cadvisor, promtail
```

### 13.2 — Verify service health

```bash
# Prometheus:
curl http://192.168.127.10:9090/-/ready
# Expected: "Prometheus Server is Ready."

# Loki:
curl http://192.168.127.10:3100/ready
# Expected: "ready"

# Jaeger:
curl http://192.168.127.10:14269/
# Expected: 200 OK

# Grafana:
curl http://192.168.127.10:3000/api/health
# Expected: {"commit":"...","database":"ok","version":"..."}

# Kong:
curl http://192.168.127.15:8001/status
# Expected: JSON with server/database status

# Spring Boot:
curl http://192.168.127.30:8080/actuator/health
# Expected: {"status":"UP"}
```

### 13.3 — Verify Prometheus scrape targets

Open `http://192.168.127.10:9090/targets` in your browser. All 13 targets should show **State: UP** (green). If any show DOWN:
- Check if the service is running on that VM
- Check firewall rules (`ufw status`)
- Check if the port is correct

### 13.4 — Verify distributed tracing

```bash
# Send a request through Kong → Spring Boot:
curl http://192.168.127.15:8000/api/employees

# Open Jaeger UI: http://192.168.127.10:16686
# Select service "kong-gateway" → Find Traces
# You should see a trace with spans from both kong-gateway and react-springboot-app
```

### 13.5 — Verify log shipping

Open Grafana (`http://192.168.127.10:3000`), go to Explore → select Loki datasource:
```
{host="application-vm"}
```
You should see logs from the application VM.

### 13.6 — Verify cross-pillar correlation

In Grafana Explore (Loki datasource), find a log line containing `trace_id=...`. Click the trace ID link — it should open the trace in Jaeger. This confirms trace-log correlation is working.

---

<a name="appendix-a"></a>
## Appendix A — Troubleshooting

### "Connection refused" when accessing a service

```bash
# Check if container is running:
docker ps | grep <service-name>

# Check container logs for errors:
docker logs <container-name> --tail 50

# Check if port is listening:
ss -tlnp | grep <port>

# Check firewall:
sudo ufw status
```

### Ansible fails with "Unreachable"

```bash
# Test SSH manually:
ssh -i ~/.ssh/ansible_key deploy@192.168.127.10

# If that works, check ansible.cfg points to the right key
# If that fails, check the VM is running and SSH is enabled
```

### Prometheus target shows "DOWN"

1. SSH to the target VM
2. Try to curl the metrics endpoint locally: `curl localhost:9100/metrics`
3. If that works, it's a firewall issue between VMs
4. If that fails, the exporter container isn't running

### No traces in Jaeger

1. Check OTel agent is attached: look for `opentelemetry-javaagent` in Spring Boot logs
2. Check endpoint: the `OTEL_EXPORTER_OTLP_ENDPOINT` must be `http://192.168.127.10:4317` (not 14268!)
3. Check Jaeger is receiving: `curl http://192.168.127.10:14269/metrics | grep otelcol_receiver_accepted_spans`
4. Check firewall: port 4317 must be open on monitoring-vm

### Traces from Kong and Spring Boot are separate (not linked)

- Verify Kong uses `header_type: w3c`
- Verify Spring Boot OTel agent uses `OTEL_PROPAGATORS: "tracecontext,baggage"` (default)
- Check that Kong actually forwards the `traceparent` header (look at Spring Boot request headers in debug logs)

### Loki shows "no logs found"

1. Check Promtail is running on the target VM
2. Check Promtail can reach Loki: `curl http://192.168.127.10:3100/ready` from the target VM
3. Check Promtail config has the correct `__path__` for the log files
4. Check the log files actually exist: `ls -la /var/log/app/` or `/var/log/kong/`

### Grafana "datasource not found" error

1. Check provisioning file exists: `ls /etc/grafana/provisioning/datasources/`
2. Check Grafana logs: `docker logs grafana --tail 50`
3. Verify the datasource URLs point to `localhost` (Grafana is on the same VM as Prometheus/Loki/Jaeger)

---

<a name="appendix-b"></a>
## Appendix B — Complete File Map

Every file in the project, what it does, and who uses it:

```
monitoring-project/
├── ansible.cfg                                    # Ansible configuration (SSH key, inventory path, sudo)
├── site.yml                                       # Master playbook — runs everything
├── implementation-steps.md                        # This document
├── CLAUDE.md                                      # AI assistant instructions
├── README.md                                      # Project documentation + architecture
│
├── inventory/
│   ├── int.yml                                    # Server list (IPs, groups, connection details)
│   └── group_vars/
│       ├── all.yml                                # Variables for ALL hosts (packages, endpoints)
│       ├── monitoring.yml                         # Monitoring VM variables (ports, scrape targets)
│       ├── application.yml                        # App VM variables (DB creds, OTel config)
│       └── network.yml                            # Network VM variables (Kong config, plugins)
│
├── roles/
│   ├── common/                                    # Runs on ALL VMs
│   │   ├── tasks/main.yml                         # Packages, timezone, firewall
│   │   ├── tasks/node_exporter.yml                # Deploy node_exporter container
│   │   ├── tasks/cadvisor.yml                     # Deploy cAdvisor container
│   │   ├── templates/node-exporter-compose.yml.j2 # Docker Compose for node_exporter
│   │   ├── templates/cadvisor-compose.yml.j2      # Docker Compose for cAdvisor
│   │   └── handlers/main.yml                      # Restart handlers
│   │
│   ├── docker/                                    # Runs on ALL VMs
│   │   ├── tasks/main.yml                         # Install Docker CE + Compose plugin
│   │   └── handlers/main.yml                      # Restart Docker daemon
│   │
│   ├── prometheus/                                # Runs on monitoring-vm
│   │   ├── defaults/main.yml                      # Default vars (version, paths)
│   │   ├── tasks/main.yml                         # Deploy Prometheus
│   │   ├── templates/prometheus.yml.j2            # Scrape configuration (13 targets)
│   │   ├── templates/docker-compose.yml.j2        # Docker Compose
│   │   └── handlers/main.yml                      # Restart handler
│   │
│   ├── loki/                                      # Runs on monitoring-vm
│   │   ├── defaults/main.yml                      # Default vars
│   │   ├── tasks/main.yml                         # Deploy Loki
│   │   ├── templates/loki-config.yml.j2           # Loki server config (schema, retention, limits)
│   │   ├── templates/docker-compose.yml.j2        # Docker Compose
│   │   └── handlers/main.yml                      # Restart handler
│   │
│   ├── jaeger/                                    # Runs on monitoring-vm
│   │   ├── defaults/main.yml                      # Default vars (ports, Badger config)
│   │   ├── tasks/main.yml                         # Deploy Jaeger v2
│   │   ├── templates/jaeger-config.yaml.j2        # Jaeger v2 OTel Collector-style config
│   │   ├── templates/docker-compose.yml.j2        # Docker Compose
│   │   ├── files/ui-config.json                   # Jaeger UI customization
│   │   └── handlers/main.yml                      # Restart handler
│   │
│   ├── grafana/                                   # Runs on monitoring-vm
│   │   ├── defaults/main.yml                      # Default vars
│   │   ├── tasks/main.yml                         # Deploy Grafana
│   │   ├── templates/datasources.yml.j2           # Auto-provision Prometheus + Loki + Jaeger
│   │   ├── templates/dashboard-provider.yml.j2    # Dashboard file provider config
│   │   ├── templates/docker-compose.yml.j2        # Docker Compose
│   │   └── handlers/main.yml                      # Restart handler
│   │
│   ├── promtail/                                  # Runs on application-vm + network-vm
│   │   ├── defaults/main.yml                      # Default vars
│   │   ├── tasks/main.yml                         # Deploy Promtail
│   │   ├── templates/promtail-config.yml.j2       # Per-host log scrape config (conditional)
│   │   ├── templates/docker-compose.yml.j2        # Docker Compose
│   │   └── handlers/main.yml                      # Restart handler
│   │
│   ├── app/                                       # Runs on application-vm
│   │   ├── defaults/main.yml                      # Default vars (paths)
│   │   ├── tasks/main.yml                         # Download OTel agent, deploy app stack
│   │   ├── templates/docker-compose.yml.j2        # 4 containers: MySQL, Spring Boot, React, MySQL Exporter
│   │   ├── templates/init.sql.j2                  # MySQL init script (grant monitoring perms)
│   │   ├── templates/mysql-exporter.cnf.j2        # MySQL exporter credentials
│   │   └── handlers/main.yml                      # Restart handler
│   │
│   ├── kong/                                      # Runs on network-vm
│   │   ├── defaults/main.yml                      # Default vars (version)
│   │   ├── tasks/main.yml                         # Deploy Kong
│   │   ├── templates/kong.yml.j2                  # Declarative config (routes + plugins)
│   │   ├── templates/docker-compose.yml.j2        # Docker Compose
│   │   └── handlers/main.yml                      # Restart handler
│   │
│   └── otel-collector/                            # OPTIONAL — not implemented (direct export is simpler)
│       └── (empty — see "Trace Pipeline Options" in README)
```

**Total: 43 files** (excluding empty dirs and this document)

---

<a name="appendix-c"></a>
## Appendix C — Future Enhancements

After the MVP demo (Sprint 2), the following enhancements are planned for deployment on CIRES private cloud:

### Sprint 2 MVP (in progress):
- **Drain3 anomaly detection** — unsupervised log pattern clustering integrated into AI triage pipeline
- **LLM triage service** — FastAPI + Ollama for automated root cause analysis
- **Full AI RCA pipeline** — alert → context → anomaly detection → LLM reasoning → email notification

### Future sprints (on private cloud):
- Jaeger MCP + System Metadata MCP for richer AI context
- WATCH state re-checker with APScheduler
- Deep prompt engineering and AI pipeline test suite
- Infrastructure as Code tooling for private cloud provisioning
- Credential hardening with Ansible Vault

**Note:** Kubernetes is out of scope for this project. The deployment model is Ansible + docker-compose on VMs (CIRES private cloud).

---

## Summary

You've built a complete observability platform:

| What | Tool | Where it runs |
|---|---|---|
| Metrics collection | Prometheus | monitoring-vm :9090 |
| Log aggregation | Loki | monitoring-vm :3100 |
| Distributed tracing | Jaeger v2 | monitoring-vm :16686 |
| Unified dashboard | Grafana | monitoring-vm :3000 |
| Log shipping | Promtail | app-vm + network-vm |
| Host metrics | node_exporter | all VMs :9100 |
| Container metrics | cAdvisor | all VMs :8081 |
| App instrumentation | OTel Java agent | app-vm (Spring Boot) |
| API Gateway + tracing | Kong | network-vm :8000 |
| Database metrics | MySQL Exporter | app-vm :9104 |
| Automation | Ansible | control node |

**To redeploy from scratch:** `ansible-playbook site.yml`

**Next steps:**
- Drain3 anomaly detection + LLM triage service (Sprint 2 MVP, in progress)
- Jaeger MCP + System Metadata MCP for richer AI context
- Private cloud deployment (same Ansible playbooks, new inventory)
