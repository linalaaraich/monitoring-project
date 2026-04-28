"""Chaos test: shrink spring-boot memory limit + load → HighMemoryUsage.

Sets the cgroup limit to 384Mi (well below the JVM's default heap on a
1Gi container, which was the original D-K case). Without ANY load, the
JVM bootstraps and idles in ~250-300Mi, which already pushes utilisation
above the HighMemoryUsage threshold. Whether the OOM-kill happens
depends on traffic — but the alert fires either way.

Teardown: restore the original limit + rollout restart so the pod gets
healthy resources back.
"""
from __future__ import annotations

import logging

from ..lib.ssh_actions import (
    k3s_get_resource_value,
    k3s_rollout_restart,
    k3s_rollout_status,
    k3s_set_resources,
)
from .base import ChaosTest

logger = logging.getLogger(__name__)


class HighMemoryUsageTest(ChaosTest):
    name = "HighMemoryUsage — spring-boot limit lowered to 384Mi"
    description = "Reduces spring-boot's memory limit so the JVM's natural footprint pushes utilisation above the alert threshold."
    expected_alertname = "HighMemoryUsage"
    timeout_s = 600

    async def setup(self) -> None:
        original = await k3s_get_resource_value(
            "spring-boot", "app",
            ".spec.template.spec.containers[?(@.name=='spring-boot')].resources.limits.memory",
        )
        self._original_limit = original or "1Gi"
        logger.info("setup: captured memory limit = %r", self._original_limit)

    async def induce(self) -> None:
        # Both --limits AND --requests must be lowered together — kubectl
        # rejects a patch that leaves request > limit. The first run
        # 2026-04-28 11:38 hit this exact validation error.
        logger.info("induce: lowering spring-boot memory limit + request to 384Mi/256Mi")
        res = await k3s_set_resources(
            "spring-boot", "app",
            limits="memory=384Mi",
            requests="memory=256Mi",
        )
        if not res.ok:
            raise RuntimeError(f"kubectl set resources failed: {res.stderr}")
        # Force the change to take effect by rolling. The new pod will
        # boot under the tight limit and quickly exceed the alert threshold.
        await k3s_rollout_restart("spring-boot", "app")

    async def teardown(self) -> None:
        limit = getattr(self, "_original_limit", "1Gi")
        logger.info("teardown: restoring spring-boot memory limit to %s + request to 512Mi", limit)
        # Restore both limit AND request so the deployment is healthy. The
        # original request value isn't captured (would need a second
        # jsonpath lookup) so we set a conservative 512Mi which fits under
        # any reasonable limit ≥ 512Mi.
        res = await k3s_set_resources(
            "spring-boot", "app",
            limits=f"memory={limit}",
            requests="memory=512Mi",
        )
        if not res.ok:
            logger.error("teardown set-resources failed: %s", res.stderr)
            return
        await k3s_rollout_restart("spring-boot", "app")
        await k3s_rollout_status("spring-boot", "app", timeout_s=120)
