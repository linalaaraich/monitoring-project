"""Chaos test: write novel error log lines from inside spring-boot → Drain3.

Triggers Drain3's self-fire by emitting a batch of log lines with a
template Drain3 has never seen before. The lines go to the pod's stdout
(PID 1's fd 1), get scraped by Promtail/whatever ships logs to Loki,
get pulled by Drain3's background ingest loop, get classified as
NEW_PATTERN, push the batch's anomaly rate above the threshold, and
fire /webhook/drain3 → triage produces a Drain3AnomalyDetected RCA.

After 2026-04-28 PM (the F-1 fix), the webhook now carries the actual
template strings + line samples — so this test is also the live
verification that the Drain3 evidence flow is repaired.

Teardown: nothing to do — the log lines are past, the templates remain
in Drain3's tree (which is intentional, that's how learning works).
"""
from __future__ import annotations

import logging
import time

from ..lib.ssh_actions import k3s_exec_in_pod, k3s_get_pod_for_deploy
from .base import ChaosTest

logger = logging.getLogger(__name__)


class Drain3AnomalyTest(ChaosTest):
    name = "Drain3AnomalyDetected — novel log template injected"
    description = "Writes 50 lines of a never-before-seen error template to spring-boot's stdout."
    expected_alertname = "Drain3AnomalyDetected"
    timeout_s = 360  # Drain3 polls every 30s; alert needs ≥20 lines + 2% rate

    async def setup(self) -> None:
        # V2 (2026-04-28 PM): emit 5 DISTINCT novel templates × 6 each
        # instead of 50× one template. V1 collapsed to one cluster after
        # the first few lines, so per-batch anomaly rate stayed at 0.47%
        # — below the 2% threshold. 5 distinct shapes mean 5 new
        # clusters, all flagged anomalous; 30 lines / batch is enough to
        # cross the 2% rate threshold.
        self._sentinel = f"chaos-{int(time.time())}"
        self._templates = [
            f"ERROR {self._sentinel}-A: JDBC connection pool exhausted at OrderService.findByDate",
            f"WARN {self._sentinel}-B: GC overhead limit exceeded after 3500ms in heap",
            f"ERROR {self._sentinel}-C: Unsupported JSON token in payload at /api/employees/import",
            f"FATAL {self._sentinel}-D: Liquibase migration v3.4.7 failed: relation already exists",
            f"ERROR {self._sentinel}-E: Tomcat thread pool reached maxThreads=200 — rejecting requests",
        ]

    async def induce(self) -> None:
        pod = await k3s_get_pod_for_deploy("spring-boot", "app")
        if not pod:
            raise RuntimeError("No spring-boot pod found")
        logger.info(
            "induce: emitting 30 lines (5 templates × 6) of novel content to %s stdout",
            pod,
        )
        # 6 reps per template so Drain3 has multiple samples to confirm
        # the cluster shape, but each TEMPLATE is unique so they don't
        # collapse together.
        loop_body = ""
        for tpl in self._templates:
            # Single quotes around tpl, escaped with shell concatenation.
            loop_body += f"for i in 1 2 3 4 5 6; do echo '{tpl} attempt='$i >> /proc/1/fd/1; done; "
        cmd = loop_body + "echo wrote 30 lines"
        res = await k3s_exec_in_pod(pod, "app", cmd, timeout_s=20)
        if not res.ok:
            raise RuntimeError(f"log injection failed: {res.stderr}")

    async def teardown(self) -> None:
        # Nothing to undo — the log lines are immutable history; they're
        # already past Loki's ingestion buffer by the time we get here.
        # Drain3 keeps the new template in its tree, which is intentional
        # (next firing of the same template won't be flagged anomalous).
        return None
