# roles/gpu_driver

Installs the NVIDIA GPU driver on a **bare Ubuntu** host so the AI tier can use
the card. Built for an NVIDIA **L4 / Ada Lovelace** (also fine for A10G etc.),
but the driver package is overridable.

## What it does

1. Checks whether `nvidia-smi` already works — if so, the whole install is
   **skipped** (idempotent).
2. Installs `ubuntu-drivers-common`, then either:
   - `gpu_driver_install_method: package` (default) — installs the pinned
     `gpu_driver_package`, or
   - `gpu_driver_install_method: autodetect` — runs `ubuntu-drivers install`.
3. Re-probes `nvidia-smi` and verifies the GPU is visible.

## The reboot caveat (important)

A fresh driver install almost always needs **one reboot** before the kernel
module loads and `nvidia-smi` works. This role **does not auto-reboot**. Instead:

- With `gpu_driver_require_smi: true` (default) it **fails** with a clear
  message telling you to `sudo reboot` and re-run. On the second run the install
  is skipped (driver already present) and the downstream GPU roles proceed.
- With `gpu_driver_require_smi: false` it only **warns** and continues (the
  downstream `nvidia_docker` / `ollama` GPU access will not work until you
  reboot).

So a from-scratch bring-up is typically: run → reboot → run again.

## Variables

| Variable | Default | Purpose |
|---|---|---|
| `gpu_driver_install_method` | `package` | `package` (pinned) or `autodetect` |
| `gpu_driver_package` | `nvidia-driver-535-server` | Pinned driver (branch >= 535 for L4) |
| `gpu_driver_require_smi` | `true` | Fail (vs warn) if `nvidia-smi` not live post-install |

Requires `become: true` (apt + driver install).
