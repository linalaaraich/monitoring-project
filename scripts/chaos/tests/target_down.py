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
    timeout_s = 360

    async def setup(self) -> None:
        return None

    async def induce(self) -> None:
        pod = await k3s_get_pod_for_deploy("spring-boot", "app")
        if not pod:
            raise RuntimeError("No spring-boot pod found")
        logger.info("induce: kill -TERM 1 inside %s", pod)
        # `kill 1` on PID 1 in a container terminates the container, k8s
        # then creates a fresh one (RESTARTS counter increments). The 30s
        # gap between old-pod-down and new-pod-ready is what TargetDown
        # detects. Some shells don't have `kill` builtin so use the
        # explicit /bin/kill path; fallback to /usr/bin/kill if absent.
        res = await k3s_exec_in_pod(
            pod, "app",
            "kill -TERM 1 || /bin/kill -TERM 1 || /usr/bin/kill -TERM 1",
            timeout_s=15,
        )
        # Don't fail on kill exec — the connection drops as soon as PID 1
        # dies, which surfaces as a non-zero exit code from kubectl exec.
        # That's expected.
        logger.info("induce: kill issued (rc=%s, stderr=%r)", res.rc, res.stderr[:80])

    async def teardown(self) -> None:
        logger.info("teardown: wait for spring-boot to be ready again")
        await k3s_rollout_status("spring-boot", "app", timeout_s=120)
