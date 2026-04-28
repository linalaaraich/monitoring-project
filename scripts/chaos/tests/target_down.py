"""Chaos test: kill the spring-boot pod's PID 1 → brief downtime → TargetDown.

V1 / V2 history is in the chaos README. V3 (this version): kill PID 1
inside the running pod via kubectl exec. SIGTERM tears down spring-boot
in seconds; while k8s spins up the replacement, scrapes against the
old endpoint return up=0 for ~30-60s — long enough for the rule to
fire (the rule has `for: 1m` so transient drops trigger).

Teardown: nothing to undo — the pod is recreated by the deployment
controller automatically. We just wait for it to be ready again so
subsequent tests run against a healthy stack.
"""
from __future__ import annotations

import logging

from ..lib.ssh_actions import (
    k3s_exec_in_pod,
    k3s_get_pod_for_deploy,
    k3s_rollout_status,
)
from .base import ChaosTest

logger = logging.getLogger(__name__)


class TargetDownTest(ChaosTest):
    name = "TargetDown — spring-boot PID 1 killed"
    description = "kubectl exec into spring-boot and kill PID 1; pod restarts; up=0 during the gap → TargetDown fires."
    expected_alertname = "TargetDown"
    timeout_s = 600  # Bumped 360→600s 2026-04-28 PM: chaos run 3 saw the alert
                     # fire ~5min after the 360s window expired (k8s pod recovery
                     # takes longer than the rule's `for: 2m` is designed for).

    async def setup(self) -> None:
        return None

    async def induce(self) -> None:
        # V4 (2026-04-28 PM): single kill produced only ~30-60s of downtime,
        # but TargetDown rule has `for: 2m`. Need sustained downtime. Loop:
        # kill PID 1, wait 25s, kill the new pod's PID 1, wait 25s, etc.
        # for 4 iterations = ~140s of cumulative downtime which beats the
        # 2m for-clause. Each kill triggers a new pod creation; we re-fetch
        # the pod name each iteration.
        import asyncio as _asyncio
        for attempt in range(1, 5):  # 4 kills × ~30s each ≈ 120s
            pod = await k3s_get_pod_for_deploy("spring-boot", "app")
            if not pod:
                logger.info("induce: no pod (attempt %d) — waiting", attempt)
                await _asyncio.sleep(15)
                continue
            logger.info("induce: kill -TERM 1 attempt %d inside %s", attempt, pod)
            res = await k3s_exec_in_pod(
                pod, "app",
                "kill -TERM 1 || /bin/kill -TERM 1 || /usr/bin/kill -TERM 1",
                timeout_s=15,
            )
            logger.info("induce: kill #%d issued (rc=%s)", attempt, res.rc)
            if attempt < 4:
                await _asyncio.sleep(25)

    async def teardown(self) -> None:
        logger.info("teardown: wait for spring-boot to be ready again")
        await k3s_rollout_status("spring-boot", "app", timeout_s=120)
