# AWS Cost Justification — Demo Environment
**Project:** Intelligent Monitoring & AI Root Cause Analysis System
**Company:** CIRES Technologies — Tanger Med
**Date:** 2026-03-30
**Prepared by:** Observability Team

---

## 1. Executive Summary

This document justifies the AWS infrastructure costs required to host a **demo environment** for the observability platform with AI-powered Root Cause Analysis (RCA). AWS is used **exclusively for the demo presentation** — the production system will be deployed on CIRES private cloud infrastructure. The monitored application is a small-scale sample stack (`react-springboot-mysql`), not production workloads.

All data — including LLM inference — stays within company-controlled infrastructure. **No data is sent to external AI APIs.**

Infrastructure is provisioned with **Terraform** (IaC) and configured with the existing **Ansible** playbooks — the same playbooks used locally. Terraform provisions the AWS resources; Ansible deploys the observability stack on top.

**Estimated cost: $82–$240 for the demo sprint (depending on usage schedule). AWS resources will be terminated after the demo.**

---

## 2. Business Justification

### Why AWS for the demo?
- Local development machines lack GPU resources for self-hosted LLM inference
- The demo on April 9, 2026 requires a reachable, stable environment accessible to supervisor and stakeholders
- AWS provides quick provisioning of a GPU instance for the Ollama LLM — avoids hardware procurement delays
- **AWS is only for the demo** — all subsequent development and production deployment will be on CIRES private cloud infrastructure

### What we're demonstrating
- Full observability stack (metrics, logs, traces) monitoring a **small-scale sample application** (`react-springboot-mysql`)
- AI-powered RCA: alert fires → system gathers context from Prometheus + Loki → self-hosted LLM analyzes → produces root cause analysis → sends email notification
- End-to-end pipeline: load test → alert → AI triage → RCA email
- The monitored system is intentionally small-scale — the goal is to validate the AI RCA architecture, not to stress-test infrastructure

### Expected Impact
- **Proof of concept** validating the AI RCA architecture before private cloud deployment
- **Reduced MTTR** demonstrated through automated root cause analysis on the sample stack
- **Production-like architecture** — the demo uses the same tier separation (S3 frontend, EC2 backend, managed RDS database, dedicated monitoring and AI instances) that production will use, validating the architecture end-to-end before migrating to CIRES private cloud

---

## 3. Architecture — Production-Like Demo

The demo uses a **production-like architecture** to validate the same patterns that will be used on CIRES private cloud. Rather than bundling everything into docker-compose on VMs, each tier is deployed to the appropriate AWS service: static frontend on S3/CloudFront, backend on EC2, database on managed RDS, and the observability + AI layers on dedicated EC2 instances.

The monitored application is a **small-scale sample stack** (React + Spring Boot + MySQL) generating minimal traffic via a load-test script — not production workloads.

### Provisioning Approach: Terraform + Ansible

| Layer | Tool | What it does |
|-------|------|-------------|
| **Infrastructure** | Terraform | Provisions VPC, subnets, security groups, EC2 instances, RDS, S3/CloudFront, EBS volumes, Elastic IPs, and start/stop automation |
| **Configuration** | Ansible | Deploys Docker, observability stack, backend application, and AI services onto the EC2 instances |

Terraform outputs (instance IPs, RDS endpoint, S3 bucket name, CloudFront domain) feed directly into the Ansible inventory. This two-layer approach means:
- Infrastructure is **reproducible** — `terraform apply` recreates the entire environment in minutes
- **Teardown is instant** — `terraform destroy` removes all AWS resources cleanly after the demo
- **No manual console work** — everything is version-controlled and auditable

### EC2 Instances

| VM | AWS Instance | Purpose | vCPUs | RAM | Storage |
|----|-------------|---------|-------|-----|---------|
| Monitoring VM | t3.large | Prometheus, Grafana, Loki, Jaeger, OTel Collector, Alertmanager | 2 | 8 GB | 50 GB gp3 |
| Backend VM | t3.small | Spring Boot API (no MySQL — database is on RDS) | 2 | 2 GB | 20 GB gp3 |
| Network VM | t3.small | Kong API Gateway | 2 | 2 GB | 20 GB gp3 |
| **AI/LLM VM** | **g4dn.xlarge** | **Ollama (self-hosted LLM), FastAPI RCA Triage Service** | **4** | **16 GB + 16 GB VRAM** | **50 GB gp3** |

### Managed Services

| Service | AWS Resource | Purpose | Spec |
|---------|-------------|---------|------|
| **Database** | RDS db.t3.micro | MySQL (single-AZ) | 2 vCPUs, 1 GB RAM, 20 GB gp3 |
| **Frontend** | S3 + CloudFront | React static build (HTML/JS/CSS) | Standard S3 bucket + CloudFront CDN |

### Why this architecture?

- **Production-like separation:** Each tier (frontend, backend, database, monitoring, AI) runs on the service best suited for it — just as it would in production. This validates the architecture before migrating to CIRES private cloud.
- **S3 + CloudFront for React:** Static files don't need a running server. S3 hosting with CloudFront CDN is how production React apps are served — cheaper, faster, and more scalable than an Nginx container.
- **RDS for MySQL:** Managed database with automated backups, patching, and a dedicated endpoint. Separating the database from the backend EC2 mirrors production best practices and avoids resource contention.
- **t3.small (Backend):** Without MySQL co-located, Spring Boot alone needs minimal resources. 2 GB RAM is sufficient for a demo-scale API.
- **t3.large (Monitoring):** Prometheus, Loki, and Jaeger need memory. 8 GB is comfortable for a demo-scale deployment with short retention.
- **t3.small (Network):** Kong in dbless mode is lightweight.
- **g4dn.xlarge (AI/LLM):** Most cost-effective GPU instance. NVIDIA T4 (16 GB VRAM) runs quantized 7B–8B models (Mistral 7B, Llama 3 8B) with good inference speed. Sufficient for MVP demo.

### Why not CPU-only for the LLM?

| | GPU (g4dn.xlarge) | CPU-only (r6i.xlarge) |
|---|---|---|
| Inference time per RCA | 5–15 seconds | 60–180 seconds |
| Cost/hr | $0.526 | $0.252 |
| Demo viability | Responsive, realistic | Too slow for live demo |

The GPU instance is essential for a convincing demo. A 2-minute wait per RCA would undermine the value proposition.

---

## 4. Cost Breakdown

### Region: us-east-1 (N. Virginia) — lowest cost

us-east-1 offers the lowest on-demand pricing for all four instance types. Although eu-west-3 (Paris) is geographically closer to Morocco, it costs ~14% more across the board. For a demo environment with no latency-sensitive end users, the cost savings outweigh the ~100ms additional latency.

#### Scenario A: GPU runs only during work hours (Recommended)

| Resource | Spec | Unit Cost | Usage | Monthly Cost |
|----------|------|-----------|-------|-------------|
| Monitoring VM | t3.large | $0.0832/hr | 730 hrs (24/7) | $60.74 |
| Backend VM | t3.small | $0.0208/hr | 730 hrs (24/7) | $15.18 |
| Network VM | t3.small | $0.0208/hr | 730 hrs (24/7) | $15.18 |
| AI/LLM VM | g4dn.xlarge | $0.526/hr | **220 hrs (10h × 22d)** | $115.72 |
| RDS MySQL | db.t3.micro | $0.017/hr | 730 hrs (24/7) | $12.41 |
| S3 + CloudFront | React frontend | — | — | ~$1.00 |
| EBS Storage | 140 GB gp3 (EC2s) | $0.08/GB | — | $11.20 |
| RDS Storage | 20 GB gp3 | $0.08/GB | — | $1.60 |
| Elastic IPs | 4 | $3.65/ea | — | $14.60 |
| Data transfer | ~30 GB | ~$0.09/GB | — | $2.70 |
| **Monthly Total** | | | | **~$250** |

#### Scenario B: All instances only during work hours

For maximum savings, stop all EC2 instances and RDS outside work hours (the demo app doesn't need 24/7 uptime):

| Resource | Usage | Monthly Cost |
|----------|-------|-------------|
| All 4 EC2s + RDS (work hours only, 10h × 22d) | 220 hrs each | |
| Monitoring VM | 220 hrs | $18.30 |
| Backend VM | 220 hrs | $4.58 |
| Network VM | 220 hrs | $4.58 |
| AI/LLM VM | 220 hrs | $115.72 |
| RDS MySQL | 220 hrs | $3.74 |
| S3 + CloudFront + storage + networking | — | $31.00 |
| **Monthly Total** | | **~$178** |

#### For the 2-week MVP sprint only (April target)

| Scenario | Estimated Cost |
|----------|---------------|
| Work hours only, all resources (10h × 10 working days) | **~$82** |
| Work hours + some evenings (14h × 14 days) | **~$146** |
| Full 24/7 for 2 weeks | **~$240** |

---

## 5. Cost Controls

| Measure | Detail |
|---------|--------|
| **Terraform destroy** | **Single command tears down all AWS resources.** No orphaned instances or forgotten volumes. `terraform destroy` is the exit plan. |
| **Start/stop schedule** | Terraform-provisioned Lambda or EventBridge rule stops all instances outside 8:00–18:00 MAT. No need for 24/7 uptime — this is a demo environment. |
| **Billing alerts** | CloudWatch billing alarm at $100, $200, and $300 thresholds → email notification |
| **Resource tagging** | All resources tagged `project:observability-rca`, `environment:demo`, `team:cires-intern` for cost tracking (enforced in Terraform) |
| **Teardown plan** | **All AWS resources are terminated immediately after the demo** via `terraform destroy`. No ongoing AWS usage — production and further development will be on CIRES private cloud. |
| **Spot instances** | g4dn.xlarge spot is ~$0.16–0.20/hr (60–70% cheaper). Viable for pre-demo testing, not for demo day itself. Can be toggled via a Terraform variable. |

---

## 6. Security & Data Sovereignty

| Requirement | Implementation |
|------------|----------------|
| **Self-hosted LLM** | Ollama running open-weight models (Llama 3 8B / Mistral 7B). No API calls to OpenAI, Anthropic, or any third-party. |
| **Network isolation** | VPC with private subnets. RDS in private subnet (no public access). Only Grafana, Kong, and CloudFront exposed. Security groups limited to CIRES IP ranges. |
| **Access control** | SSH key-pair only. IAM user with scoped permissions. MFA enabled. All infrastructure defined in Terraform — no manual console changes. |
| **No production data** | Demo uses the sample React + Spring Boot app. No real CIRES business data on AWS. |
| **Demo-only** | AWS environment will be torn down immediately after the April 9 demo. No ongoing AWS usage. Production target is CIRES private cloud. |

---

## 7. AWS vs Private Cloud Roadmap

| Phase | Infrastructure | Tooling | Timeline |
|-------|---------------|---------|----------|
| **Demo** | AWS (EC2, RDS, S3/CloudFront) | Terraform + Ansible | April 9, 2026 |
| **Teardown** | `terraform destroy` — all AWS resources removed | Terraform | Immediately after demo |
| **Development & Production** | CIRES private cloud | Ansible (same playbooks) | Post-demo, TBD by management |

The AWS deployment uses **Terraform** for infrastructure provisioning and **Ansible** for configuration. The production-like architecture (S3 frontend, EC2 backend, managed RDS, dedicated monitoring and AI instances) validates the same tier separation that will be used on CIRES private cloud. Migration to private cloud requires updating the Ansible inventory with new host IPs and swapping managed services (e.g., RDS → private cloud MySQL, S3 → private cloud object storage). The Terraform layer is AWS-specific. This portability is a key design choice: AWS is a temporary hosting vehicle for the demo, not a platform commitment.

---

## 8. Summary

| Item | Detail |
|------|--------|
| **What** | Production-like AWS environment: 4 EC2 instances (3 standard + 1 GPU), RDS MySQL, S3 + CloudFront |
| **Why** | AI RCA demo on April 9; local machines lack GPU for LLM inference; production-like architecture validates the design before private cloud migration |
| **Provisioning** | **Terraform** (infrastructure) + **Ansible** (configuration) — fully automated, version-controlled |
| **Architecture** | S3/CloudFront (frontend) + EC2 (backend) + RDS (database) + EC2 (monitoring) + EC2 GPU (AI/LLM) — mirrors production tier separation |
| **Scope** | Small-scale sample app (`react-springboot-mysql`), not production workloads |
| **Duration** | Demo only — AWS resources terminated immediately after April 9 demo |
| **Cost** | **~$82–$240** depending on usage schedule (work hours only recommended) |
| **Data safety** | Self-hosted LLM, no external APIs, sample data only, VPC isolated, RDS in private subnet |
| **Exit plan** | `terraform destroy` removes all AWS resources. All further work on CIRES private cloud. |
