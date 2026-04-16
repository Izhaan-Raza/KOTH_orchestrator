# KOTH_orchestrator Deployment Runbook (Linear)

This guide is intentionally linear:

1. Set up `node1`, `node2`, `node3` first.
2. Set up `referee` host second.
3. Load balancer (HAProxy) is on the same host as referee.

No separate LB machine is used.

## 0) Fixed Topology and Naming

Use these hosts (example):

1. `node1`: `nodeA@192.168.0.102`
2. `node2`: `recon_admin@192.168.0.103`
3. `node3`: `nodeC@192.168.0.106`
4. `referee` (Referee API + Scheduler + HAProxy): `recon_admin@192.168.0.100`

Use `KOTH_orchestrator` naming consistently for paths.

## 1) Choose Install Root Once

Pick one install root and use it everywhere on all four hosts:

1. Recommended: `/opt/KOTH_orchestrator`
2. No-`/opt` fallback: `$HOME/KOTH_orchestrator`

The same logical layout must exist on all three node machines.

In commands below, `INSTALL_ROOT` means your chosen root.

## 2) Setup Node 1, Node 2, Node 3 (Do This First)

Run this full section on each of `node1`, `node2`, and `node3`.

## 2.1 Base packages + time sync

```bash
sudo apt update
sudo apt install -y git curl ca-certificates gnupg lsb-release jq chrony
sudo systemctl enable --now chrony
chronyc tracking
```

## 2.2 Docker + Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

Important:
Referee runtime executes `docker-compose ...` on nodes, so ensure `docker-compose` command exists.

```bash
sudo apt install -y docker-compose-plugin
docker-compose --version
```

If `docker-compose` is still missing, install compatibility package:

```bash
sudo apt install -y docker-compose
docker-compose --version
```

## 2.3 Clone repository

For `/opt` layout:

```bash
sudo mkdir -p /opt/KOTH_orchestrator
sudo chown -R "$USER:$USER" /opt/KOTH_orchestrator
cd /opt/KOTH_orchestrator
git clone https://github.com/Izhaan-Raza/KOTH_orchestrator.git repo
```

For `$HOME` layout:

```bash
mkdir -p "$HOME/KOTH_orchestrator"
cd "$HOME/KOTH_orchestrator"
git clone https://github.com/Izhaan-Raza/KOTH_orchestrator.git repo
```

## 2.4 Build required per-series directories

Set variable:

```bash
export INSTALL_ROOT="/opt/KOTH_orchestrator"  # or "$HOME/KOTH_orchestrator"
```

Create `h1..h8` layout expected by referee:

```bash
cd "$INSTALL_ROOT"
for i in 1 2 3 4 5 6 7 8; do
  mkdir -p "h$i"
  cp -r "$INSTALL_ROOT/repo/Series H$i/"* "$INSTALL_ROOT/h$i/"
done
```

Validate:

```bash
for i in 1 2 3 4 5 6 7 8; do
  test -f "$INSTALL_ROOT/h$i/docker-compose.yml" && echo "h$i OK" || echo "h$i MISSING"
done
```

## 2.5 Validate node locally (required)

Run:

```bash
cd "$INSTALL_ROOT/repo"
bash qa/deployment/validate_koth_node.sh --series-root "$INSTALL_ROOT"
```

Expected result: `ALL CHECKS PASSED`.

Repeat sections `2.1` to `2.5` on `node1`, `node2`, `node3`.

## 3) Setup Referee + LB on Same Host

Run this section on `referee` host only.

## 3.1 Base packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl jq chrony haproxy
sudo systemctl enable --now chrony
chronyc tracking
```

## 3.2 Clone repository

For `/opt` layout:

```bash
sudo mkdir -p /opt/KOTH_orchestrator
sudo chown -R "$USER:$USER" /opt/KOTH_orchestrator
cd /opt/KOTH_orchestrator
git clone https://github.com/Izhaan-Raza/KOTH_orchestrator.git repo
```

For `$HOME` layout:

```bash
mkdir -p "$HOME/KOTH_orchestrator"
cd "$HOME/KOTH_orchestrator"
git clone https://github.com/Izhaan-Raza/KOTH_orchestrator.git repo
```

Set:

```bash
export INSTALL_ROOT="/opt/KOTH_orchestrator"  # or "$HOME/KOTH_orchestrator"
cd "$INSTALL_ROOT/repo/referee-server"
```

## 3.3 Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3.4 SSH key from referee to all nodes

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/koth_referee -N ""
```

Install key on nodes:

```bash
ssh-copy-id -i ~/.ssh/koth_referee.pub nodeA@192.168.0.102
ssh-copy-id -i ~/.ssh/koth_referee.pub recon_admin@192.168.0.103
ssh-copy-id -i ~/.ssh/koth_referee.pub nodeC@192.168.0.106
```

Record host keys:

```bash
ssh-keyscan -H 192.168.0.102 192.168.0.103 192.168.0.106 >> ~/.ssh/known_hosts
chmod 600 ~/.ssh/known_hosts
```

Quick SSH test:

```bash
ssh -i ~/.ssh/koth_referee nodeA@192.168.0.102 "hostname"
ssh -i ~/.ssh/koth_referee recon_admin@192.168.0.103 "hostname"
ssh -i ~/.ssh/koth_referee nodeC@192.168.0.106 "hostname"
```

## 3.5 Referee `.env` (critical)

Create `"$INSTALL_ROOT/repo/referee-server/.env"`:

```env
APP_HOST=0.0.0.0
APP_PORT=8000
DB_PATH=./referee.db

NODE_HOSTS=192.168.0.102,192.168.0.103,192.168.0.106
NODE_PRIORITY=192.168.0.102,192.168.0.103,192.168.0.106

SSH_USER=<common-node-ssh-user>
SSH_PORT=22
SSH_PRIVATE_KEY=~/.ssh/koth_referee
SSH_TIMEOUT_SECONDS=8
SSH_STRICT_HOST_KEY_CHECKING=true

VARIANTS=A,B,C
TOTAL_SERIES=8
POLL_INTERVAL_SECONDS=30
ROTATION_INTERVAL_SECONDS=3600
POINTS_PER_CYCLE=1.0
MAX_CLOCK_DRIFT_SECONDS=2

REMOTE_SERIES_ROOT=/opt/KOTH_orchestrator
CONTAINER_NAME_TEMPLATE=machineH{series}{variant}

BACKEND_URL=
WEBHOOK_URL=
ADMIN_API_KEY=replace-with-long-random-value
MIN_HEALTHY_NODES=2
```

If using `$HOME` layout, set:

1. `REMOTE_SERIES_ROOT=/home/<node-user>/KOTH_orchestrator`
2. This path must exist identically on all node machines.

Generate a strong API key:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

## 3.6 HAProxy config on referee host

Edit `/etc/haproxy/haproxy.cfg` with frontends/backends for your exposed game ports.

Minimal H1 example:

```cfg
global
  daemon

defaults
  mode tcp
  timeout connect 5s
  timeout client  2m
  timeout server  2m

frontend h1a
  bind *:10001
  default_backend h1a_nodes
backend h1a_nodes
  balance roundrobin
  server n1 192.168.0.102:10001 check
  server n2 192.168.0.103:10001 check
  server n3 192.168.0.106:10001 check

frontend h1b
  bind *:10002
  default_backend h1b_nodes
backend h1b_nodes
  balance roundrobin
  server n1 192.168.0.102:10002 check
  server n2 192.168.0.103:10002 check
  server n3 192.168.0.106:10002 check

frontend h1c
  bind *:10004
  default_backend h1c_nodes
backend h1c_nodes
  balance roundrobin
  server n1 192.168.0.102:10004 check
  server n2 192.168.0.103:10004 check
  server n3 192.168.0.106:10004 check
```

Validate and start:

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
sudo systemctl enable --now haproxy
sudo systemctl restart haproxy
```

## 3.7 Start referee

Preflight:

```bash
cd "$INSTALL_ROOT/repo/referee-server"
source .venv/bin/activate
python setup_cli.py --series 1
```

Manual run:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Notes:

1. `referee-server` auto-loads `./.env`, so manual `uvicorn` and `setup_cli.py` use the same configuration as systemd.
2. Startup fails if `ADMIN_API_KEY` is empty unless `ALLOW_UNSAFE_NO_ADMIN_API_KEY=true`.
3. Startup also fails if no teams exist locally and `BACKEND_URL` does not provide `/teams`.

Or systemd service:

```ini
[Unit]
Description=KOTH Referee Server
After=network.target

[Service]
Type=simple
User=<YOUR_USER>
WorkingDirectory=<INSTALL_ROOT>/repo/referee-server
EnvironmentFile=<INSTALL_ROOT>/repo/referee-server/.env
ExecStart=<INSTALL_ROOT>/repo/referee-server/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Replace `<INSTALL_ROOT>` with your actual value before saving the unit file.
Example:

1. `/opt/KOTH_orchestrator`
2. `/home/<user>/KOTH_orchestrator`

## 3.8 Validate referee+LB host (required)

```bash
cd "$INSTALL_ROOT/repo"
bash qa/deployment/validate_referee_lb.sh \
  --series-root "$INSTALL_ROOT" \
  --referee-dir "$INSTALL_ROOT/repo/referee-server" \
  --api-url "http://127.0.0.1:8000"
```

Expected result: `ALL CHECKS PASSED`.

## 4) Operational API Commands

```bash
export REFEREE_URL="http://10.0.0.20:8000"
export API_KEY="<admin_api_key>"
```

Start:

```bash
curl -sS -X POST "$REFEREE_URL/api/competition/start" -H "X-API-Key: $API_KEY"
```

Runtime status:

```bash
curl -sS "$REFEREE_URL/api/runtime" | jq .
```

Rotate:

```bash
curl -sS -X POST "$REFEREE_URL/api/rotate" -H "X-API-Key: $API_KEY"
```

Pause/Resume:

```bash
curl -sS -X POST "$REFEREE_URL/api/pause" -H "X-API-Key: $API_KEY"
curl -sS -X POST "$REFEREE_URL/api/resume" -H "X-API-Key: $API_KEY"
```

Validate / Recover faulted or paused series:

```bash
curl -sS -X POST "$REFEREE_URL/api/recover/validate" -H "X-API-Key: $API_KEY" | jq .
curl -sS -X POST "$REFEREE_URL/api/recover/redeploy" -H "X-API-Key: $API_KEY" | jq .
```

Lifecycle guidance:

1. `paused` means the current series is still expected to be valid, but scoring and rotation are halted.
2. `faulted` means the runtime detected an unsafe series state or failed recovery path. Do not use `resume` until validation or redeploy succeeds.
3. Use `/api/runtime` for operator truth. It exposes `competition_status`, `previous_series`, `fault_reason`, `last_validated_series`, and active jobs.

Stop:

```bash
curl -sS -X POST "$REFEREE_URL/api/competition/stop" -H "X-API-Key: $API_KEY"
```

## 5) Final Pre-Go-Live Order

1. Validate `node1` using `validate_koth_node.sh`
2. Validate `node2` using `validate_koth_node.sh`
3. Validate `node3` using `validate_koth_node.sh`
4. Validate `referee` using `validate_referee_lb.sh`
5. Start competition
6. Confirm `/api/runtime` reports `running` and no `fault_reason`
7. Begin live traffic
