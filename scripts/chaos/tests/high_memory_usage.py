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
    name = "PodHighMemoryUsage — spring-boot pod cgroup pressure"
    description = "Reduces spring-boot's memory limit so the JVM's natural footprint pushes the pod's container_memory_working_set / container_spec_memory_limit ratio above 85%."
    expected_alertname = "PodHighMemoryUsage"
    timeout_s = 600

    async def setup(self) -> None:
        original = await k3s_get_resource_value(
            "spring-boot", "app",
            ".spec.template.spec.containers[?(@.name=='spring-boot')].resources.limits.memory",
        )
        self._original_limit = original or "1Gi"
        logger.info("setup: captured memory limit = %r", self._original_limit)

    async def induce(self) -> None:
        # V3 (2026-04-28 13:00 PM): drop the limit further AND pair with
        # in-pod synthetic load. V2's 384Mi limit + idle JVM landed at
        # only ~250Mi (65% utilisation) — below the alert threshold.
        # 256Mi forces the JVM to bump against the cgroup; the curl loop
        # generates real request work that allocates objects on the heap.
        logger.info("induce: lowering spring-boot memory limit + request to 256Mi/192Mi")
        res = await k3s_set_resources(
            "spring-boot", "app",
            limits="memory=256Mi",
            requests="memory=192Mi",
        )
        if not res.ok:
            raise RuntimeError(f"kubectl set resources failed: {res.stderr}")
        # Force the change to take effect by rolling. The new pod will
        # boot under the tight limit and quickly exceed the alert threshold.
        await k3s_rollout_restart("spring-boot", "app")
        # Generate synthetic load so heap pressure is real. Kong front-door
        # at NodePort 30080. Loop fires concurrent requests in background
        # so the test continues without blocking.
        from ..lib.ssh_actions import ssh_exec, K3S_HOST, K3S_USER
        load_cmd = (
            "for i in $(seq 1 600); do "
            "(curl -s -o /dev/null -m 3 http://localhost:30080/api/employees &); "
            "(curl -s -o /dev/null -m 3 http://localhost:30080/api/employees &); "
            "(curl -s -o /dev/null -m 3 http://localhost:30080/api/employees &); "
            "sleep 0.3; "
            "done > /dev/null 2>&1 &"
        )
        await ssh_exec(K3S_HOST, K3S_USER, load_cmd, timeout_s=10)
        logger.info("induce: started 3-concurrent curl loop against /api/employees for ~3 min")

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
