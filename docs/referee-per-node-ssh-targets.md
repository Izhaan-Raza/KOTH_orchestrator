# Referee Per-Node SSH Targets

## Summary

The referee previously assumed every challenge node used the same SSH username from `SSH_USER`.
That breaks in deployments where nodes expose different accounts.

The referee now supports optional per-node SSH targets through `NODE_SSH_TARGETS`.

## Environment Variable

Add `NODE_SSH_TARGETS` to `referee-server/.env` when node usernames differ:

```env
NODE_HOSTS=192.168.0.70,192.168.0.103,192.168.0.106
NODE_PRIORITY=192.168.0.70,192.168.0.103,192.168.0.106
NODE_SSH_TARGETS=nodeA@192.168.0.70,nodeB@192.168.0.103,nodeC@192.168.0.106
```

Rules:

- `NODE_SSH_TARGETS` must contain the same number of comma-separated entries as `NODE_HOSTS`.
- Each entry should be `user@host` for the corresponding node.
- `user@host` overrides `SSH_USER` for that node.

## Current Deployment Example

The current cluster uses mixed SSH identities:

- `nodeA@192.168.0.70`
- `nodeB@192.168.0.103`
- `nodeC@192.168.0.106`

Use:

```env
NODE_HOSTS=192.168.0.70,192.168.0.103,192.168.0.106
NODE_PRIORITY=192.168.0.70,192.168.0.103,192.168.0.106
NODE_SSH_TARGETS=nodeA@192.168.0.70,nodeB@192.168.0.103,nodeC@192.168.0.106
SSH_USER=root
SSH_PRIVATE_KEY=~/.ssh/koth_referee
```

`SSH_USER=root` remains a fallback default, but this deployment should rely on `NODE_SSH_TARGETS`.

## Verification

```bash
cd referee-server
source .venv/bin/activate
python setup_cli.py --series 1
```

Expected result:

- each node reports working Docker and `docker-compose`
- each node reports `H1 compose: OK`

## Code Paths

- `referee-server/config.py`
- `referee-server/ssh_client.py`
- `referee-server/app.py`
- `referee-server/setup_cli.py`
- `referee-server/tests/test_ssh_targets.py`
