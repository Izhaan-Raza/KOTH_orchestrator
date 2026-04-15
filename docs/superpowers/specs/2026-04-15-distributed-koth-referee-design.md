# Distributed KOTH Referee System - Design Specification (V2)

**Date:** 2026-04-15

**Status:** Approved - Revised for High Availability & Load Balancing

## Overview

Refactor the KOTH orchestrator to a load-balanced 3-machine cluster with a centralized referee server. The referee acts as a watchdog that manages lifecycle actions across all nodes, enforces violation rules, and scores teams using an "Earliest Change" consensus that tolerates replication lag.

## Key Corrections Applied

- **Replicated topology:** Each node runs `A`, `B`, and `C` for the active series (9 containers total).
- **Scoring unit:** Points are awarded per **variant** (`A/B/C`), not per node, to avoid triple-counting the same replicated state.
- **Consensus tie-break:** If `mtime` is identical across nodes, winner is chosen by deterministic node priority (`Node1`, `Node2`, `Node3`) to remove ambiguity.
- **Time-sync prerequisite:** All challenge nodes and referee must run NTP/chrony; if drift exceeds configured threshold, affected node is marked `degraded` and excluded from earliest-change resolution until recovered.
- **Global enforcement:** A violation seen on any node is applied to the owning team globally.

## Architecture

### Physical Layout

- **Load Balancer (LB):** Distributes inbound player traffic across all challenge nodes.
- **Machine-1 (Node 1):** Runs `HnA`, `HnB`, `HnC` for current series `n`.
- **Machine-2 (Node 2):** Runs `HnA`, `HnB`, `HnC` for current series `n`.
- **Machine-3 (Node 3):** Runs `HnA`, `HnB`, `HnC` for current series `n`.
- **Referee Server:** FastAPI + scheduler + SQLite. Reaches nodes directly over SSH on VLAN.

## Competition Parameters

- 24 problems = 8 series (`H1..H8`) * 3 variants (`A/B/C`)
- 8 hours total, 1 series/hour
- Poll interval: 30s
- Up to 300 teams / 600 players
- Points: `1 point` per poll cycle per variant held
- Max per variant/hour: `120`
- Max total/hour: `360`

## Polling and Earliest-Change Resolution

Every 30 seconds:

1. Referee polls Node1/Node2/Node3 in parallel.
2. For each node and each variant (`A/B/C`), it reads:
   - `/root/king.txt` content
   - `stat -c '%Y %a %U:%G %F' /root/king.txt`
3. For each variant, referee chooses winning ownership by:
   - Keep only valid team claims (not `unclaimed`, not malformed)
   - Select the smallest `%Y` (`mtime` epoch)
   - If tie: apply node priority tie-break
4. Award one point for that variant to winning team.
5. Run violation detection on each node; apply offense globally to team.

### Batched SSH Probe

```bash
echo "===KING===";
cat /root/king.txt 2>/dev/null || echo "FILE_MISSING";
echo "===KING_STAT===";
stat -c '%Y %a %U:%G %F' /root/king.txt 2>/dev/null || echo "STAT_FAIL";
echo "===ROOT_DIR===";
stat -c '%a' /root 2>/dev/null;
echo "===IMMUTABLE===";
lsattr /root/king.txt 2>/dev/null || echo "NO_LSATTR";
# ... remaining checks unchanged ...
```

## Rotation Flow

For `Hn -> H(n+1)`:

1. Pre-rotation: final poll, log event, fire webhook, reset `series_banned` to `warned`.
2. Teardown on all nodes in parallel: `docker-compose down -v --remove-orphans`.
3. Deploy next series on all nodes in parallel: `docker-compose up -d --force-recreate`.
4. Health-check all 9 containers (running, ports, `king.txt=unclaimed`).
5. Capture new baselines across all variants/nodes.
6. Resume polling with updated `current_series`.

## Data Model Change

### containers

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto increment |
| machine_host | TEXT | Node IP |
| variant | TEXT | `A` / `B` / `C` |
| container_id | TEXT | e.g. `H3A_Node1` |
| series | INTEGER | Active series |
| status | TEXT | `running/stopped/crashed/rotating/failed/unreachable/degraded` |
| last_checked | TIMESTAMP | Last successful probe |

## Deployment Layout on Each Challenge Node

```text
/opt/koth/
+-- h1/
|   +-- docker-compose.yml   # starts H1A/H1B/H1C on this node
|   +-- machineH1A/
|   +-- machineH1B/
|   +-- machineH1C/
+-- h2/
|   +-- docker-compose.yml
|   +-- ...
```
