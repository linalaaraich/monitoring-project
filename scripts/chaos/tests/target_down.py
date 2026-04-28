"""Chaos test: break spring-boot's readiness probe → triggers TargetDown.

V1 of this test scaled the deploy to 0 replicas. That removes the pod
from the SD entirely (no pod = no `up` series), so TargetDown
(`up == 0`) never fires. Verified live 2026-04-28 11:29 — 8 min poll
with no alert.

V2 (this version): patch the readinessProbe to point at a non-existent
path. The pod stays up (still in SD), the kubelet reports it as not
ready, scrapes go through the SDN to a probe that returns 404, the
proxy considers the upstream down, and the `up` series flips to 0.
TargetDown fires within 1-2 scrape intervals (~1 min).

Teardown: kubectl rollout undo restores the previous (working) probe
config. Tested as the standard k8s rollback path.
"""
from __future__ import annotations

import logging
import shlex

from ..lib.ssh_actions import k3s_kubectl, k3s_rollout_status
from .base import ChaosTest

logger = logging.getLogger(__name__)


class TargetDownTest(ChaosTest):
    name = "TargetDown — spring-boot readiness probe broken"
    description = "Patches spring-boot's readiness probe to a non-existent path; pod stays in SD but probes fail → up=0 → TargetDown fires."
    expected_alertname = "TargetDown"
    timeout_s = 360  # ~6min — readiness probe + scrape + alert eval typically <2min

    async def setup(self) -> None:
        # No pre-state to capture — `kubectl rollout undo` reverts to the
        # working revision regardless of what it was.
        return None

    async def induce(self) -> None:
        # JSON-patch the readiness probe to point at a path that returns 404.
        # Spring Boot's actuator returns 404 on unknown paths (not 503), but
        # k8s readiness gating treats any 4xx/5xx as failed. Replaces the
        # whole probe object so we don't have to know the existing shape.
        patch = '{"spec":{"template":{"spec":{"containers":[{"name":"spring-boot","readinessProbe":{"httpGet":{"path":"/__chaos_no_such_path","port":8080},"initialDelaySeconds":1,"periodSeconds":3,"failureThreshold":1}}]}}}}'
        logger.info("induce: patching spring-boot readiness probe to bad path")
        res = await k3s_kubectl(
            f"patch deploy/spring-boot -n app --type=strategic -p {shlex.quote(patch)}"
        )
        if not res.ok:
            raise RuntimeError(f"kubectl patch failed: {res.stderr}")

    async def teardown(self) -> None:
        logger.info("teardown: kubectl rollout undo on spring-boot")
        res = await k3s_kubectl("rollout undo deploy/spring-boot -n app")
        if not res.ok:
            logger.error("teardown rollout undo failed: %s", res.stderr)
            return
        await k3s_rollout_status("spring-boot", "app", timeout_s=120)
