# Referee Per-Node SSH Targets

## Summary

The referee previously assumed every challenge node used the same SSH username from `SSH_USER`.
That breaks in deployments where nodes expose different accounts.

The referee now supports optional per-node SSH targets through `NODE_SSH_TARGETS`.

## Environment Variable

Add `NODE_SSH_TARGETS` to `referee-server/.env` when node usernames differ:

```env
NODE_HOSTS=192.168.0.102,192.168.0.103,192.168.0.106
NODE_PRIORITY=192.168.0.102,192.168.0.103,192.168.0.106
NODE_SSH_TARGETS=nodeA@192.168.0.102,recon_admin@192.168.0.103,nodeC@192.168.0.106
```

Rules:

- `NODE_SSH_TARGETS` is optional.
- If it is omitted, the referee uses `SSH_USER` for every node.
- If it is present, it must contain the same number of comma-separated entries as `NODE_HOSTS`.
- Each entry may be either `user@host` or just `host`.
- `user@host` overrides `SSH_USER` for that node only.
- A bare `host` entry falls back to `SSH_USER`.

## Compatibility

Clusters with a shared username do not need to change anything. This still works:

```env
SSH_USER=root
NODE_HOSTS=10.0.0.11,10.0.0.12,10.0.0.13
```

and `NODE_SSH_TARGETS` can remain unset.

## Current Deployment Example

The current cluster uses mixed SSH identities:

- `nodeA@192.168.0.102`
- `recon_admin@192.168.0.103`
- `nodeC@192.168.0.106`

Use:

```env
NODE_HOSTS=192.168.0.102,192.168.0.103,192.168.0.106
NODE_PRIORITY=192.168.0.102,192.168.0.103,192.168.0.106
NODE_SSH_TARGETS=nodeA@192.168.0.102,recon_admin@192.168.0.103,nodeC@192.168.0.106
SSH_USER=root
SSH_PRIVATE_KEY=~/.ssh/koth_referee
```

`SSH_USER=root` remains the default and is ignored for nodes that have explicit `user@host` overrides.

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
