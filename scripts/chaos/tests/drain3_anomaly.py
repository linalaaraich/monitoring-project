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
        # Generate a unique sentinel string so the template is guaranteed novel
        # (contains the timestamp). Drain3 collapses similar messages into one
        # cluster, so we only need one shape — repeated 50 times to push the
        # batch's anomaly rate above threshold.
        self._sentinel = f"chaos-{int(time.time())}"
        self._template_phrase = (
            f"ERROR ChaosTest {self._sentinel}: simulated novel failure mode at "
            f"OrderService.injectedFault — synthetic anomaly for chaos audit"
        )

    async def induce(self) -> None:
        pod = await k3s_get_pod_for_deploy("spring-boot", "app")
        if not pod:
            raise RuntimeError("No spring-boot pod found")
        logger.info("induce: emitting 50 lines of novel template to %s stdout", pod)
        # Write 50 copies to /proc/1/fd/1 (the pod's PID 1 stdout, which is
        # what Promtail tails). Use a single shell loop so it's one exec call.
        cmd = (
            f"i=0; while [ $i -lt 50 ]; do "
            f"echo '{self._template_phrase} attempt='$i >> /proc/1/fd/1; "
            f"i=$((i+1)); done; echo wrote 50 lines"
        )
        res = await k3s_exec_in_pod(pod, "app", cmd, timeout_s=15)
        if not res.ok:
            raise RuntimeError(f"log injection failed: {res.stderr}")

    async def teardown(self) -> None:
        # Nothing to undo — the log lines are immutable history; they're
        # already past Loki's ingestion buffer by the time we get here.
        # Drain3 keeps the new template in its tree, which is intentional
        # (next firing of the same template won't be flagged anomalous).
        return None
