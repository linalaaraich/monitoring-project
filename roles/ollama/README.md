# roles/ollama

Installs **Ollama as a host systemd unit** (not a container) and pulls the
triage models. The triage containers reach it at `host.docker.internal:11434`.

## What it does

1. Installs the `ollama` binary via the official installer
   (`https://ollama.com/install.sh`), **skipped if `ollama` is already on PATH**.
   The installer also lays down the `ollama` systemd unit + system user.
2. Installs a systemd drop-in setting `OLLAMA_HOST=0.0.0.0:11434` (gated on
   `ollama_bind_all`, default true). **This is required** — by default Ollama
   binds `127.0.0.1`, which a container cannot reach via
   `host.docker.internal` (that points at the host's bridge-gateway IP, not
   loopback). Without the drop-in the triage stack gets connection-refused.
3. Enables + starts the service and waits for `:11434`.
4. Pulls every model in `ollama_models` that `ollama list` doesn't already
   show, **async** (multi-GB downloads).

## Variables

| Variable | Default | Purpose |
|---|---|---|
| `ollama_port` | `11434` | Listen port |
| `ollama_models` | `["qwen2.5:14b-instruct", "qwen2.5:7b-instruct"]` | Models to pull (14b primary, 7b fallback) |
| `ollama_bind_all` | `true` | Install the `OLLAMA_HOST=0.0.0.0` drop-in |
| `ollama_data_dir` | `/var/lib/ollama` | Data dir |
| `ollama_install_script_url` | `https://ollama.com/install.sh` | Installer |
| `ollama_pull_async_timeout` | `7200` | Per-model pull ceiling (s) |

Requires `become: true` (installer, systemd, drop-in).
