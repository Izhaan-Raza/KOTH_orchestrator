# Deployment Validation Checklist

Use this checklist after following `docs/full-deployment-runbook.md`.

Mark each item explicitly as:

1. `[x]` complete
2. `[ ]` not complete
3. Add notes for any failure

## A) Node1 (`nodeA@192.168.0.70`)

- [ ] `chrony` is active and synchronized
- [ ] `docker` is installed and daemon is running
- [ ] `docker compose` plugin works (or compatibility shim forwards `docker-compose` to it)
- [ ] `INSTALL_ROOT/repo` exists and is the `KOTH_orchestrator` repo
- [ ] `INSTALL_ROOT/h1..h8/docker-compose.yml` all exist
- [ ] `h1..h8` compose files contain expected `machineH{N}{A|B|C}` services
- [ ] Local validation script passes:
  - `bash qa/deployment/validate_koth_node.sh --series-root <INSTALL_ROOT>`
- [ ] Notes:

## B) Node2 (`nodeB@192.168.0.103`)

- [ ] `chrony` is active and synchronized
- [ ] `docker` is installed and daemon is running
- [ ] `docker compose` plugin works (or compatibility shim forwards `docker-compose` to it)
- [ ] `INSTALL_ROOT/repo` exists and is the `KOTH_orchestrator` repo
- [ ] `INSTALL_ROOT/h1..h8/docker-compose.yml` all exist
- [ ] `h1..h8` compose files contain expected `machineH{N}{A|B|C}` services
- [ ] Local validation script passes:
  - `bash qa/deployment/validate_koth_node.sh --series-root <INSTALL_ROOT>`
- [ ] Notes:

## C) Node3 (`nodeC@192.168.0.106`)

- [ ] `chrony` is active and synchronized
- [ ] `docker` is installed and daemon is running
- [ ] `docker compose` plugin works (or compatibility shim forwards `docker-compose` to it)
- [ ] `INSTALL_ROOT/repo` exists and is the `KOTH_orchestrator` repo
- [ ] `INSTALL_ROOT/h1..h8/docker-compose.yml` all exist
- [ ] `h1..h8` compose files contain expected `machineH{N}{A|B|C}` services
- [ ] Local validation script passes:
  - `bash qa/deployment/validate_koth_node.sh --series-root <INSTALL_ROOT>`
- [ ] Notes:

## D) Referee + LB Host (`192.168.0.12`)

- [ ] `chrony` is active and synchronized
- [ ] `haproxy` installed and config validates (`haproxy -c`)
- [ ] `haproxy` service is active
- [ ] Referee python venv exists
- [ ] `referee-server/.env` exists
- [ ] `.env` includes non-empty values:
  - `NODE_HOSTS`
  - `NODE_PRIORITY`
  - `SSH_USER`
  - `SSH_PRIVATE_KEY`
  - `REMOTE_SERIES_ROOT`
  - `CONTAINER_NAME_TEMPLATE=machineH{series}{variant}`
  - `ADMIN_API_KEY`
- [ ] If node usernames differ, `.env` includes `NODE_SSH_TARGETS` with one entry per node in `NODE_HOSTS`
- [ ] Referee runtime config validates:
  - `cd <INSTALL_ROOT>/repo/referee-server && .venv/bin/python -c "from config import SETTINGS; SETTINGS.validate_runtime()"`
- [ ] Referee service is active (or manual uvicorn run is active)
- [ ] Referee can SSH to all nodes using configured key
- [ ] `python setup_cli.py --series 1` succeeds
- [ ] Referee API `/api/status` returns valid response
- [ ] Referee API `/api/runtime` returns valid lifecycle response with:
  - `competition_status`
  - `previous_series`
  - `fault_reason`
  - `last_validated_series`
  - `healthy_nodes`, `total_nodes`, and `min_healthy_nodes` from `/api/recover/validate`
  - `active_jobs`
- [ ] Local validation script passes:
  - `bash qa/deployment/validate_referee_lb.sh --series-root <INSTALL_ROOT> --referee-dir <INSTALL_ROOT>/repo/referee-server --api-url http://127.0.0.1:8000`
- [ ] Notes:

## E) Cluster Consistency Checks

- [ ] Same `INSTALL_ROOT` model chosen everywhere (`/opt/KOTH_orchestrator` OR `$HOME/KOTH_orchestrator`)
- [ ] `REMOTE_SERIES_ROOT` in referee `.env` matches actual path on all 3 nodes
- [ ] `NODE_HOSTS` and `NODE_PRIORITY` match actual node IPs
- [ ] If `NODE_SSH_TARGETS` is set, its entries match the real `user@host` SSH targets for those same nodes
- [ ] All nodes reachable from referee via SSH
- [ ] Clock drift across nodes is within threshold during dry poll
- [ ] LB fronts the intended challenge ports
- [ ] Notes:

## F) Pre-Go-Live Signoff

- [ ] Node1 validated
- [ ] Node2 validated
- [ ] Node3 validated
- [ ] Referee+LB validated
- [ ] Dry run completed (`start -> runtime -> pause -> validate -> resume -> rotate -> stop`)
- [ ] Recovery path verified (`faulted/paused -> /api/recover/validate -> /api/recover/redeploy -> resume`)
- [ ] Team admin path verified (`/api/admin/teams -> ban -> unban`)
- [ ] Incident rollback owner assigned
- [ ] Notes:
