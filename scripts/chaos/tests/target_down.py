"""Chaos test: scale spring-boot to 0 → triggers TargetDown alert.

Cleanest of the chaos tests because the teardown is deterministic
(scale back to 1 + wait for ready). Used as the smoke test for the
runner before more invasive injections.
"""
from __future__ import annotations

import logging

from ..lib.ssh_actions import k3s_scale, k3s_rollout_status
from .base import ChaosTest

logger = logging.getLogger(__name__)


class TargetDownTest(ChaosTest):
    name = "TargetDown — spring-boot scaled to 0"
    description = "Scales spring-boot deployment to 0 replicas, expects TargetDown to fire."
    expected_alertname = "TargetDown"
    timeout_s = 480  # 8min — TargetDown fires after 2 consecutive scrape misses (~1min)

    async def setup(self) -> None:
        # Spring-boot's stable replica count is 1 in the current topology.
        # If that ever changes, this captures it dynamically.
        from ..lib.ssh_actions import k3s_get_resource_value
        original = await k3s_get_resource_value("spring-boot", "app", ".spec.replicas")
        self._original_replicas = int(original) if original.isdigit() else 1
        logger.info("setup: captured original replicas = %d", self._original_replicas)

    async def induce(self) -> None:
        logger.info("induce: scaling spring-boot to 0 replicas")
        res = await k3s_scale("spring-boot", "app", 0)
        if not res.ok:
            raise RuntimeError(f"kubectl scale failed: {res.stderr}")

    async def teardown(self) -> None:
        replicas = getattr(self, "_original_replicas", 1)
        logger.info("teardown: restoring spring-boot to %d replicas", replicas)
        res = await k3s_scale("spring-boot", "app", replicas)
        if not res.ok:
            logger.error("teardown scale-up failed: %s", res.stderr)
            return
        # Wait for the deployment to come back up so subsequent tests run on a healthy stack
        await k3s_rollout_status("spring-boot", "app", timeout_s=120)
