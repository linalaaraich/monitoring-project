# AWS Cost Justification — Demo Environment
**Project:** Intelligent Monitoring & AI Root Cause Analysis System
**Company:** CIRES Technologies — Tanger Med
**Date:** 2026-03-27
**Prepared by:** Observability Team

---

## 1. Executive Summary

This document justifies the AWS infrastructure costs required to host a **demo environment** for the observability platform with AI-powered Root Cause Analysis (RCA). AWS is used **exclusively for the demo presentation** — the production system will be deployed on CIRES private cloud infrastructure. The monitored application is a small-scale sample stack (`react-springboot-mysql`), not production workloads.

All data — including LLM inference — stays within company-controlled infrastructure. **No data is sent to external AI APIs.**

**Estimated cost: $88–$250 for the demo sprint (depending on usage schedule). AWS resources will be terminated after the demo.**

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
- **Architecture validation** — confirms the same Ansible playbooks and docker-compose templates work on cloud VMs, enabling seamless migration to CIRES private cloud

---

## 3. Architecture — Small-Scale Demo

The demo mirrors the existing 3-VM local setup plus one GPU instance for AI inference. The monitored application is a **small-scale sample stack** (React + Spring Boot + MySQL) generating minimal traffic via a load-test script — not production workloads.

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
| **Start/stop schedule** | Cron script or AWS Lambda stops all instances outside 8:00–18:00 MAT. No need for 24/7 uptime — this is a demo environment. |
| **Billing alerts** | CloudWatch billing alarm at $100, $200, and $300 thresholds → email notification |
| **Resource tagging** | All resources tagged `project:observability-rca`, `environment:demo`, `team:cires-intern` for cost tracking |
| **Teardown plan** | **All AWS resources are terminated immediately after the demo.** No ongoing AWS usage — production and further development will be on CIRES private cloud. |
| **Spot instances** | g4dn.xlarge spot is ~$0.16–0.20/hr (60–70% cheaper). Viable for pre-demo testing, not for demo day itself. |

---

## 6. Security & Data Sovereignty

| Requirement | Implementation |
|------------|----------------|
| **Self-hosted LLM** | Ollama running open-weight models (Llama 3 8B / Mistral 7B). No API calls to OpenAI, Anthropic, or any third-party. |
| **Network isolation** | VPC with private subnets. Only Grafana and Kong exposed via security groups limited to CIRES IP ranges. |
| **Access control** | SSH key-pair only. IAM user with scoped permissions. MFA enabled. |
| **No production data** | Demo uses the sample React + Spring Boot app. No real CIRES business data on AWS. |
| **Demo-only** | AWS environment will be torn down immediately after the April 9 demo. No ongoing AWS usage. Production target is CIRES private cloud. |

---

## 7. AWS vs Private Cloud Roadmap

| Phase | Infrastructure | Timeline |
|-------|---------------|----------|
| **Demo** | AWS EC2 (this request) | April 9, 2026 |
| **Teardown** | Terminate all AWS resources | Immediately after demo |
| **Development & Production** | CIRES private cloud | Post-demo, TBD by management |

The AWS deployment uses the same Ansible playbooks and docker-compose templates as the local environment. Migration to private cloud requires only updating the inventory file with new host IPs — no architectural changes. This portability is a key design choice: AWS is a temporary hosting vehicle for the demo, not a platform commitment.

---

## 8. Summary

| Item | Detail |
|------|--------|
| **What** | 4 EC2 instances (3 standard + 1 GPU) for demo environment |
| **Why** | AI RCA demo on April 9; local machines lack GPU for LLM inference |
| **Scope** | Small-scale sample app (`react-springboot-mysql`), not production workloads |
| **Duration** | Demo only — AWS resources terminated immediately after April 9 demo |
| **Cost** | **~$88–$250** depending on usage schedule (work hours only recommended) |
| **Data safety** | Self-hosted LLM, no external APIs, sample data only, VPC isolated |
| **Exit plan** | Terminate all AWS resources after demo. All further work on CIRES private cloud. |
