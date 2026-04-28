"""Primitive SSH actions for chaos tests.

All chaos tests run their kubectl/docker/shell commands by SSH-ing as
deploy@<tailnet-hostname>. The tests never run kubectl from the
controller because the kubeconfig is SG-blocked from this host (see
2026-04-28 audit) — running on the k3s host itself with `sudo k3s
kubectl` is the reliable path.

Hosts (tailnet MagicDNS):
  - observability-rca-k3s   — control-plane node (k3s)
  - adolin-wsl              — laptop running triage + Ollama
  - observability-rca-monitoring — EC2 with the docker-compose obs stack

The user `lina@` works on adolin-wsl; `deploy@` everywhere else.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
from dataclasses import dataclass

logger = logging.getLogger(__name__)

K3S_HOST = "observability-rca-k3s"
LAPTOP_HOST = "adolin-wsl"
MONITORING_HOST = "observability-rca-monitoring"

K3S_USER = "deploy"
LAPTOP_USER = "lina"
MONITORING_USER = "deploy"

SSH_KEY = "~/.ssh/ansible_key"


@dataclass
class SshResult:
    rc: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.rc == 0


async def ssh_exec(host: str, user: str, cmd: str, timeout_s: float = 30.0) -> SshResult:
    """Run a shell command via SSH. Pure subprocess, no fancy wrapping."""
    full = [
        "ssh",
        "-i", SSH_KEY.replace("~", "/root"),  # ssh inside this binary doesn't expand ~
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ConnectTimeout={int(timeout_s)}",
        f"{user}@{host}",
        cmd,
    ]
    logger.debug("ssh: %s@%s :: %s", user, host, cmd[:120])
    proc = await asyncio.create_subprocess_exec(
        *full,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return SshResult(rc=124, stdout="", stderr=f"ssh timed out after {timeout_s}s")
    return SshResult(
        rc=proc.returncode or 0,
        stdout=out.decode(errors="replace").strip(),
        stderr=err.decode(errors="replace").strip(),
    )


# ---------------------------------------------------------------------------
# k3s helpers (run on the k3s host, sudo k3s kubectl ...)
# ---------------------------------------------------------------------------

async def k3s_kubectl(args: str, timeout_s: float = 30.0) -> SshResult:
    """Run `sudo k3s kubectl <args>` on the k3s control-plane node."""
    return await ssh_exec(K3S_HOST, K3S_USER, f"sudo k3s kubectl {args}", timeout_s=timeout_s)


async def k3s_scale(deploy: str, namespace: str, replicas: int) -> SshResult:
    return await k3s_kubectl(f"scale deploy/{deploy} -n {namespace} --replicas={replicas}")


async def k3s_set_resources(
    deploy: str, namespace: str, *, limits: str | None = None, requests: str | None = None
) -> SshResult:
    flags = []
    if limits:
        flags.append(f"--limits={limits}")
    if requests:
        flags.append(f"--requests={requests}")
    return await k3s_kubectl(f"set resources deploy/{deploy} -n {namespace} {' '.join(flags)}")


async def k3s_rollout_restart(deploy: str, namespace: str) -> SshResult:
    return await k3s_kubectl(f"rollout restart deploy/{deploy} -n {namespace}")


async def k3s_rollout_status(deploy: str, namespace: str, timeout_s: int = 90) -> SshResult:
    return await k3s_kubectl(
        f"rollout status deploy/{deploy} -n {namespace} --timeout={timeout_s}s",
        timeout_s=timeout_s + 10,
    )


async def k3s_get_pod_for_deploy(deploy: str, namespace: str) -> str | None:
    """Return the first Running pod name matching the deployment in the namespace.

    Tries the standard helm/k8s label first (app.kubernetes.io/name=<deploy>)
    and falls back to the simpler app=<deploy> shape. Picks Running pods only
    to avoid grabbing a Terminating pod mid-rollout.
    """
    selectors = [
        f"app.kubernetes.io/name={deploy}",
        f"app={deploy}",
    ]
    for sel in selectors:
        res = await k3s_kubectl(
            f"get pods -n {namespace} -l {sel} --field-selector=status.phase=Running "
            f"--no-headers -o custom-columns=NAME:.metadata.name | head -1"
        )
        name = res.stdout.strip()
        if name:
            return name
    return None


async def k3s_exec_in_pod(pod: str, namespace: str, cmd: str, timeout_s: float = 30.0) -> SshResult:
    """Run a command inside a pod via `kubectl exec`. cmd is the shell string."""
    quoted = shlex.quote(cmd)
    return await k3s_kubectl(
        f"exec -n {namespace} {pod} -- sh -c {quoted}",
        timeout_s=timeout_s,
    )


async def k3s_get_resource_value(deploy: str, namespace: str, jsonpath: str) -> str:
    """Fetch a single jsonpath value from a deployment."""
    res = await k3s_kubectl(
        f"get deploy/{deploy} -n {namespace} -o jsonpath='{{{jsonpath}}}'"
    )
    return res.stdout.strip()


# ---------------------------------------------------------------------------
# Triage data plane (the chaos test reads from /decisions on the laptop)
# ---------------------------------------------------------------------------

async def http_get(url: str, timeout_s: float = 8.0) -> SshResult:
    """Curl helper for triage HTTP endpoints — runs locally on the controller."""
    proc = await asyncio.create_subprocess_exec(
        "curl", "-sS", "--max-time", str(int(timeout_s)), url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return SshResult(
        rc=proc.returncode or 0,
        stdout=out.decode(errors="replace").strip(),
        stderr=err.decode(errors="replace").strip(),
    )
