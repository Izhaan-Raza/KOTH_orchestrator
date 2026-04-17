# Deployment Validation Scripts

These scripts validate host setup after deployment.

## 1) On each KOTH node (`node1`, `node2`, `node3`)

```bash
bash qa/deployment/validate_koth_node.sh --series-root /opt/KOTH_orchestrator
```

If using home layout:

```bash
bash qa/deployment/validate_koth_node.sh --series-root "$HOME/KOTH_orchestrator"
```

## 2) On referee+LB host

```bash
bash qa/deployment/validate_referee_lb.sh \
  --series-root /opt/KOTH_orchestrator \
  --referee-dir /opt/KOTH_orchestrator/repo/referee-server \
  --api-url http://127.0.0.1:8000
```

If using home layout:

```bash
bash qa/deployment/validate_referee_lb.sh \
  --series-root "$HOME/KOTH_orchestrator" \
  --referee-dir "$HOME/KOTH_orchestrator/repo/referee-server" \
  --api-url http://127.0.0.1:8000
```

Both scripts exit non-zero if validation fails.

## 2.5) Emulate referee SSH and team creation locally

Use this to prove the referee bootstrap paths without touching live nodes or a live backend:

```bash
python qa/deployment/emulate_referee_paths.py \
  --series 1 \
  --hosts 192.168.0.70,192.168.0.103,192.168.0.106 \
  --teams "Team Alpha,Team Beta"
```

This emulates:

1. the SSH/docker checks from `referee-server/setup_cli.py`
2. local team-roster creation in a temporary SQLite `referee.db`

## 3) Pre-build Docker image cache on challenge nodes

Use this before the first competition start so `docker-compose up -d` does not
time out while building images on the nodes:

```bash
bash qa/deployment/prebuild_series_cache.sh \
  --referee-dir /opt/KOTH_orchestrator/repo/referee-server
```

Useful variants:

```bash
# Build only H1 on all nodes
bash qa/deployment/prebuild_series_cache.sh --series 1

# Build H1 and H2 on a single node
bash qa/deployment/prebuild_series_cache.sh --series 1,2 --hosts 192.168.0.70

# Force base-image refresh during build
bash qa/deployment/prebuild_series_cache.sh --pull
```
