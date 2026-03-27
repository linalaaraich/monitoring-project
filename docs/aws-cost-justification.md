# AWS Cost Justification — Demo Environment
**Project:** Intelligent Monitoring & AI Root Cause Analysis System
**Company:** CIRES Technologies — Tanger Med
**Date:** 2026-03-27
**Prepared by:** Observability Team

---

## 1. Executive Summary

This document justifies the AWS infrastructure costs required to host a **temporary demo environment** for the observability platform with AI-powered Root Cause Analysis (RCA). AWS is used exclusively for demonstration and development — the production system will be deployed on CIRES private cloud infrastructure.

All data — including LLM inference — stays within company-controlled infrastructure. **No data is sent to external AI APIs.**

**Estimated cost: $150–$250 for a 2-week demo sprint, ~$300–$500/month if kept running during development.**

---

## 2. Business Justification

### Why AWS (temporarily)?
- Local development machines lack GPU resources for self-hosted LLM inference
- Team members need remote access to the demo environment for collaboration
- Supervisor demo on April 9, 2026 requires a reachable, stable environment
- Production deployment target is CIRES private cloud — AWS is a stepping stone

### What we're demonstrating
- Full observability stack (metrics, logs, traces) monitoring a small-scale application
- AI-powered RCA: alert fires → system gathers context from Prometheus + Loki → self-hosted LLM analyzes → produces root cause analysis → sends email notification
- End-to-end pipeline: load test → alert → AI triage → RCA email

### Expected Impact
- **Reduced MTTR** through automated root cause analysis
- **24/7 automated triage** — no dependency on engineer availability for initial analysis
- **Proof of concept** validating the architecture before private cloud deployment

---

## 3. Architecture — Small-Scale Demo

The demo mirrors the existing 3-VM local setup plus one GPU instance for AI inference. The monitored application is a small-scale React + Spring Boot + MySQL stack — not production traffic.

| VM | AWS Instance | Purpose | vCPUs | RAM | Storage |
|----|-------------|---------|-------|-----|---------|
| Monitoring VM | t3.large | Prometheus, Grafana, Loki, Jaeger, OTel Collector, Alertmanager | 2 | 8 GB | 50 GB gp3 |
| Application VM | t3.medium | Spring Boot, MySQL, Promtail | 2 | 4 GB | 30 GB gp3 |
| Network VM | t3.small | Kong API Gateway, Promtail | 2 | 2 GB | 20 GB gp3 |
| **AI/LLM VM** | **g4dn.xlarge** | **Ollama (self-hosted LLM), RCA Triage Service** | **4** | **16 GB + 16 GB VRAM** | **50 GB gp3** |

### Why these instance types?

- **t3.large (Monitoring):** Prometheus, Loki, and Jaeger need memory. 8 GB is comfortable for a demo-scale deployment with short retention.
- **t3.medium (Application):** Spring Boot + MySQL for a demo app. Minimal load.
- **t3.small (Network):** Kong in dbless mode is lightweight.
- **g4dn.xlarge (AI/LLM):** Most cost-effective GPU instance. NVIDIA T4 (16 GB VRAM) runs quantized 7B–8B models (Mistral 7B, Llama 3 8B) with good inference speed. Sufficient for MVP demo. No need for the pricier g5 instances at this stage.

### Why not CPU-only for the LLM?

| | GPU (g4dn.xlarge) | CPU-only (r6i.xlarge) |
|---|---|---|
| Inference time per RCA | 5–15 seconds | 60–180 seconds |
| Cost/hr | $0.526 | $0.252 |
| Demo viability | Responsive, realistic | Too slow for live demo |

The GPU instance is essential for a convincing demo. A 2-minute wait per RCA would undermine the value proposition.

---

## 4. Cost Breakdown

### Region: eu-west-3 (Paris) — nearest to Morocco

#### Scenario A: GPU runs only during work hours (Recommended)

| Resource | Spec | Unit Cost | Usage | Monthly Cost |
|----------|------|-----------|-------|-------------|
| Monitoring VM | t3.large | $0.0832/hr | 730 hrs (24/7) | $60.74 |
| Application VM | t3.medium | $0.0416/hr | 730 hrs (24/7) | $30.37 |
| Network VM | t3.small | $0.0208/hr | 730 hrs (24/7) | $15.18 |
| AI/LLM VM | g4dn.xlarge | $0.526/hr | **220 hrs (10h × 22d)** | $115.72 |
| EBS Storage | 150 GB gp3 total | $0.08/GB | — | $12.00 |
| Elastic IPs | 4 | $3.65/ea | — | $14.60 |
| Data transfer | ~30 GB | ~$0.09/GB | — | $2.70 |
| **Monthly Total** | | | | **~$251** |

#### Scenario B: All instances only during work hours

For maximum savings, stop all instances outside work hours (the demo app doesn't need 24/7 uptime):

| Resource | Usage | Monthly Cost |
|----------|-------|-------------|
| All 4 VMs (work hours only, 10h × 22d) | 220 hrs each | |
| Monitoring VM | 220 hrs | $18.30 |
| Application VM | 220 hrs | $9.15 |
| Network VM | 220 hrs | $4.58 |
| AI/LLM VM | 220 hrs | $115.72 |
| Storage + networking | — | $29.30 |
| **Monthly Total** | | **~$177** |

#### For the 2-week MVP sprint only (April target)

| Scenario | Estimated Cost |
|----------|---------------|
| Work hours only, all VMs (10h × 10 working days) | **~$88** |
| Work hours + some evenings (14h × 14 days) | **~$150** |
| Full 24/7 for 2 weeks | **~$250** |

---

## 5. Cost Controls

| Measure | Detail |
|---------|--------|
| **Start/stop schedule** | Cron script or AWS Lambda stops GPU instance outside 8:00–18:00 MAT. Base VMs can also be stopped if 24/7 access isn't needed. |
| **Billing alerts** | CloudWatch billing alarm at $100, $200, and $300 thresholds → email notification |
| **Resource tagging** | All resources tagged `project:observability-rca`, `environment:demo`, `team:cires-intern` for cost tracking |
| **Teardown plan** | Once demo is complete and architecture is validated, all AWS resources are terminated. Production runs on private cloud. |
| **Spot instances** | g4dn.xlarge spot is ~$0.16–0.20/hr (60–70% cheaper). Viable for development, not for demo day. |

---

## 6. Security & Data Sovereignty

| Requirement | Implementation |
|------------|----------------|
| **Self-hosted LLM** | Ollama running open-weight models (Llama 3 8B / Mistral 7B). No API calls to OpenAI, Anthropic, or any third-party. |
| **Network isolation** | VPC with private subnets. Only Grafana and Kong exposed via security groups limited to CIRES IP ranges. |
| **Access control** | SSH key-pair only. IAM user with scoped permissions. MFA enabled. |
| **No production data** | Demo uses the sample React + Spring Boot app. No real CIRES business data on AWS. |
| **Temporary** | AWS environment will be torn down after demo/development phase. Production target is CIRES private cloud. |

---

## 7. AWS vs Private Cloud Roadmap

| Phase | Infrastructure | Timeline |
|-------|---------------|----------|
| **MVP Demo** | AWS EC2 (this request) | April 2026 |
| **Development & Testing** | AWS EC2 (continue if needed) | April–May 2026 |
| **Production** | CIRES private cloud | TBD by management |

The AWS deployment uses the same Ansible playbooks and docker-compose templates as the local environment. Migration to private cloud requires only updating the inventory file with new host IPs — no architectural changes.

---

## 8. Summary

| Item | Detail |
|------|--------|
| **What** | 4 EC2 instances (3 standard + 1 GPU) for demo environment |
| **Why** | AI RCA demo on April 9; team collaboration; local machines lack GPU |
| **Duration** | Temporary — 2–4 weeks for MVP, then migrate to private cloud |
| **2-week cost** | **~$88–$150** (work hours only) |
| **Monthly cap** | ~$250 with work-hours scheduling |
| **Data safety** | Self-hosted LLM, no external APIs, demo data only, VPC isolated |
| **Exit plan** | Tear down all AWS resources once private cloud is ready |
