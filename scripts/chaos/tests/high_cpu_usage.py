"""Chaos test: spawn CPU-burning processes inside spring-boot → HighCpuUsage.

`yes > /dev/null &` repeated N times — spawns sustained 100%-CPU
processes that survive the kubectl exec returning. The cgroup CPU
shares clamp them to the pod's CPU allocation, so this drives
container_cpu_usage_seconds_total up reliably.

Teardown: rollout restart kills the burner processes via pod
replacement (no need to find/kill PIDs — the new pod starts clean).
"""
from __future__ import annotations

import logging

from ..lib.ssh_actions import (
    k3s_exec_in_pod,
    k3s_get_pod_for_deploy,
    k3s_rollout_restart,
    k3s_rollout_status,
)
from .base import ChaosTest

logger = logging.getLogger(__name__)


class HighCpuUsageTest(ChaosTest):
    name = "HighCpuUsage — spring-boot CPU saturation"
    description = "Spawns 4× `yes > /dev/null` inside spring-boot to drive CPU utilisation high."
    expected_alertname = "HighCpuUsage"
    timeout_s = 480

    async def setup(self) -> None:
        # Capture current pod name so teardown is targeted (rollout creates
        # a new pod regardless, so this is mostly informational).
        self._original_pod = await k3s_get_pod_for_deploy("spring-boot", "app")
        logger.info("setup: current pod = %s", self._original_pod)

    async def induce(self) -> None:
        pod = await k3s_get_pod_for_deploy("spring-boot", "app")
        if not pod:
            raise RuntimeError("No spring-boot pod found")
        logger.info("induce: spawning 4 CPU-burner processes in %s", pod)
        # Spawn 4 yes loops; nohup + & detaches them from the kubectl exec
        # session so they keep running after the exec returns.
        cmd = "for i in 1 2 3 4; do nohup yes > /dev/null 2>&1 & done; sleep 1; echo started"
        res = await k3s_exec_in_pod(pod, "app", cmd, timeout_s=15)
        if not res.ok:
            raise RuntimeError(f"kubectl exec failed: {res.stderr}")

    async def teardown(self) -> None:
        logger.info("teardown: rollout restart spring-boot to kill burners cleanly")
        await k3s_rollout_restart("spring-boot", "app")
        await k3s_rollout_status("spring-boot", "app", timeout_s=120)
