# KoTH Orchestrator Repository Study

## Scope

This writeup explains how the repository is organized, how the production referee system works, how challenge content is packaged, and how the QA and deployment tooling fit around it. It is based on the code and manifests in this repository, not just the README.

## Repository At A Glance

| Path | What it is | Why it exists |
| --- | --- | --- |
| `referee-server/` | The real production control plane | Runs the FastAPI admin API, scheduler, scoring, enforcement, telemetry, dashboards, and recovery flows |
| `Series H1/` ... `Series H8/` | Eight challenge packs | Each series contains a `docker-compose.yml`, a local `orchestrator_hN.sh`, and three machine definitions (`A/B/C`) |
| `qa/` | Validation and test harnesses | Load probes, vuln proofs, deployment validators, and a live rule-matrix validator |
| `docs/` | Operational and design documentation | Runbooks, rule checklists, HAProxy notes, deployment docs, and design specs |
| `docker-compose.yml` | Local/dev convenience stack | Brings up all machines together; README explicitly says this is not the production control plane |
| `rotate.sh` | Legacy local round-rotation helper | Tears down the local dev stack and boots one round at a time |

## High-Level Architecture

The important architectural split is:

1. Production uses `referee-server/` plus node-local copies of per-series compose files.
2. Local development can still use the root `docker-compose.yml` and `rotate.sh`, but those are explicitly secondary.

Operationally, the control path is: operators use the admin dashboard and API, the FastAPI service talks to the SQLite state store and the `RefereeRuntime`, and the runtime uses SSH plus HAProxy control to manage and judge the replicated challenge nodes.

## Production Deployment Model

The deployment model is distributed. The referee host does not build the challenge containers itself during normal runtime. Instead:

- Each challenge node stores `h1/`, `h2/`, ... `h8/` directories under `REMOTE_SERIES_ROOT`.
- Each such directory contains the matching `Series HN/docker-compose.yml`.
- The referee SSHes into every node, changes into `.../hN`, and runs `docker compose up/down`.
- HAProxy on the referee/load-balancer host exposes only the currently active series.

In practice, the repository supplies the series compose packs, those packs are copied to node-local directories, and the referee host remotely drives those per-node deployments while keeping HAProxy aligned with whichever series is judged active.

## Top-Level Components

### `referee-server/`

This is the core of the repository.

- `app.py` builds the FastAPI admin API and participant board, wires startup/shutdown, reads HAProxy state, exposes runtime/recovery endpoints, and serves the HTML dashboards.
- `scheduler.py` owns competition lifecycle, series rotation, deploy health gates, polling, scoring, enforcement, recovery, and HAProxy state sync.
- `poller.py` probes every node/variant over SSH, parses `king.txt` and security-relevant state, and detects policy violations.
- `scorer.py` resolves winners by quorum and earliest accepted claim timestamp.
- `enforcer.py` escalates warnings to series bans and then full bans.
- `db.py` owns the SQLite schema and all persistence.
- `models.py` defines API response/request models.
- `ssh_client.py` keeps reusable Paramiko sessions and supports per-host username overrides.
- `webhook.py` asynchronously posts event payloads to an optional webhook.
- `runtime_logging.py` configures rotating logs and structured JSON event logging.
- `setup_cli.py` is a bootstrap helper that verifies Docker and compose reachability on nodes.
- `templates/` and `static/` back the admin and participant dashboards.
- `tests/` validates scoring, drift handling, recovery behavior, API auth, and SSH target overrides.

### `Series H1/` ... `Series H8/`

Each series is packaged the same way:

- `docker-compose.yml` defines the three machines for that hour.
- `orchestrator_hN.sh` is a local shell helper with `build`, `start`, `stop`, and `status`.
- `machineHNA/`, `machineHNB/`, `machineHNC/` contain the Dockerfiles and service-specific assets.

These folders are challenge content, not referee logic.

### `qa/`

This is the repo's validation harness:

- `targets.py` is the canonical target registry for ports and protocols.
- `common.py` provides HTTP/TCP/UDP helpers, JSON output helpers, and terminal table rendering.
- `load_suite.py` does concurrent service-level load probes across the exposed port matrix.
- `vuln_suite.py` runs machine-specific proof checks using marker-based payloads.
- `koth_load_sim.py` is an authorized async TCP load simulator.
- `deployment/` contains host validators, prebuild helpers, service units, path emulators, and a live rule-matrix validator.

### `docs/`

This folder is operator-facing documentation. The current contents show the project has grown beyond a simple stack runner into a managed competition platform:

- deployment and full-runbook docs
- rule and participant policy docs
- HAProxy config notes
- validation checklists
- remediation and design notes

## Referee Server Deep Dive

### Boot And Lifetime

`app.py` creates global singletons early:

- `Database`
- `SSHClientPool`
- `RefereeRuntime`

On FastAPI lifespan startup it:

1. validates environment settings
2. starts the scheduler
3. restores scheduled rotation state if the DB says competition status is already `running`

On shutdown it:

1. stops APScheduler
2. closes SSH connections

### Configuration Model

`config.py` is intentionally simple and fail-closed:

- It loads env vars first, then optional `.env` files.
- It supports per-node SSH targets via `NODE_SSH_TARGETS`.
- It validates that `ADMIN_API_KEY` exists unless explicitly disabled.
- It validates node counts, variants, timeouts, and `MIN_HEALTHY_NODES`.

Key settings drive nearly all runtime behavior:

- node inventory: `NODE_HOSTS`, `NODE_PRIORITY`, `NODE_SSH_TARGETS`
- scoring and safety: `MIN_HEALTHY_NODES`, `MAX_CLOCK_DRIFT_SECONDS`, `POINTS_PER_CYCLE`
- deploy behavior: `REMOTE_SERIES_ROOT`, `DOCKER_COMPOSE_CMD`, deploy health timeouts
- integration: `BACKEND_URL`, `WEBHOOK_URL`

### Database Model

`db.py` stores both competition state and observability history in a single SQLite file. It is not just a score table; it is the runtime source of truth.

The most important tables are:

- `competition`: current lifecycle state, series pointers, poll counter, rotation timing, and fault reason
- `teams`: roster, offense state, and cumulative points
- `point_events`: every scoring award
- `events`: human-readable lifecycle, scoring, recovery, and enforcement event feed
- `violations`: durable record of team-attributed rule breaches
- `active_violations`: deduplication set used to prevent re-escalating the same live offense every poll
- `containers`: latest per-node, per-variant container status and observed claim state
- `baselines`: clean post-deploy hashes and signatures used for drift detection
- `variant_ownership`: current authoritative owner for each variant in a series
- `claim_observations`: every poll observation, including rejected and non-winning claims
- `public_dashboard_config` and `public_notifications`: operator-managed data for the public board

Important design choices in the schema:

- `variant_ownership` stores the authoritative winner for each variant in a series.
- `claim_observations` stores every seen claim, not just the winner.
- `active_violations` prevents re-escalating the same violation every poll cycle.
- `baselines` let the system detect drift in ports, iptables, `/etc/shadow`, and `authorized_keys`.

### Runtime State Machine

The competition state is explicit and persisted. That lets the service recover across restarts without guessing.

The allowed transitions are:

- `stopped` -> `starting` -> `running` on successful competition boot
- `starting` -> `stopped` if the first series fails health gates
- `running` -> `paused` when an operator halts rotation intentionally
- `paused` -> `running` only after successful validation
- `paused` -> `faulted` if resume validation fails
- `running` -> `rotating` during manual or scheduled series changes
- `rotating` -> `running` if deploy succeeds or rollback succeeds
- `rotating` -> `faulted` if both forward deploy and rollback fail
- `running` -> `stopping` -> `stopped` during shutdown
- `faulted` -> `rotating` -> `paused` during recovery redeploy

### Polling, Scoring, And Enforcement

The `Poller` builds one SSH probe script per series. For each variant on each node it collects:

- node epoch time
- `/root/king.txt`
- file metadata for `king.txt`
- `/root` permissions
- immutable-bit state
- cron entries
- watchdog-like processes
- iptables rules
- listening ports
- SHA-256 of `/etc/shadow`
- SHA-256 of `/root/.ssh/authorized_keys`

It parses that into `VariantSnapshot` objects and emits `ViolationHit` entries for direct rule breaches.

Then `RefereeRuntime.poll_once()` does the rest:

1. skip if competition is not `running`
2. poll all nodes for the active series
3. mark clock-drifted replicas as `degraded`
4. merge baseline-based drift violations
5. upsert container status into the DB
6. reject scoring if the snapshot matrix is incomplete
7. reject per-variant scoring if healthy quorum is below threshold
8. resolve winners via `scorer.py`
9. persist claim observations
10. change authoritative owners when quorum accepts a new team
11. award points
12. reconcile drifted replicas back to the authoritative owner
13. escalate new violations through `Enforcer`

So each poll is both an evidence-collection cycle and a full adjudication cycle. It does not merely observe; it can change ownership, assign points, reconcile replicas, and escalate punishment in the same pass.

### Winner Selection Rules

`scorer.py` is small but central. Its logic is:

- ignore non-running snapshots
- ignore missing, malformed, or `unclaimed` claims
- require `king.txt` mtime
- group remaining snapshots by variant and team
- if the current authoritative owner still holds quorum, keep it
- otherwise find teams with quorum and choose the earliest `king.txt` mtime
- break ties by `NODE_PRIORITY`, then hostname

That gives the system two desirable properties:

- sticky ownership when the current owner still legitimately holds quorum
- deterministic tie-breaking when two replicas show the same timestamp

### Violation Model

There are two layers of violation detection:

1. direct probe-time rules from `poller.py`
2. baseline drift rules from `scheduler.py`

Direct rules catch:

- wrong `king.txt` mode or ownership
- immutable bit
- deleted or non-regular `king.txt`
- `/root` permission changes
- cron persistence
- watchdog processes

Baseline rules catch:

- listener drift
- iptables drift
- `/etc/shadow` drift
- `authorized_keys` drift

Two exemptions are hard-coded:

- H1B authkeys changes
- H7B shadow changes

Those exceptions exist because those machines intentionally use those files in the intended solve path.

The escalation ladder is simple:

- offense 1 -> `warned`
- offense 2 -> `series_banned`
- offense 3+ -> `banned`

### Rotation, Recovery, And Health Gates

Rotation is not just "bring down old, bring up new". The scheduler has a full guarded flow:

1. final poll on the current series
2. mark target HAProxy listeners `maint`
3. mark current listeners `drain`
4. tear down current series on every node
5. deploy target series on every node
6. repeatedly poll until deploy health passes or timeout expires
7. settle once more after a short delay
8. capture fresh baselines for the new series
9. switch HAProxy active series

If target deploy fails:

- the system attempts rollback to the previous series
- if rollback works, runtime returns to `running`
- if rollback fails, runtime enters `faulted`

Recovery is intentionally more conservative:

- allowed only from `paused` or `faulted`
- redeploys the current series
- leaves runtime in `paused`
- requires a separate `resume`

The rotation path is therefore: freeze the current round with one final poll, drain and park the relevant HAProxy listeners, tear down the old series, deploy the target series, keep probing until deploy health is trustworthy, and either commit the new series or roll back to the previous one.

### HAProxy, Routing, And Telemetry

`app.py` does more than expose CRUD endpoints. It also makes the referee host an observability surface.

HAProxy-related functions:

- parse static listener config from `haproxy.cfg`
- query active connections using `ss`
- query runtime server status using the HAProxy admin socket
- expose `/api/lb` and `/api/routing`

Telemetry-related functions:

- collect local Linux metrics on the referee/LB host
- SSH to every node for host metrics and Docker inspection
- normalize container uptime, restart counts, health, and memory/cpu stats
- expose `/api/telemetry`

### API Surface

The API breaks into five groups.

| Group | Representative endpoints | Purpose |
| --- | --- | --- |
| dashboards | `/`, participant `/`, `/api/public/dashboard` | Serve admin and public UI |
| runtime control | `/api/competition/start`, `/api/rotate`, `/api/pause`, `/api/poll` | Operate the competition |
| recovery | `/api/recover/validate`, `/api/recover/redeploy` | Validate and redeploy after faults |
| observability | `/api/status`, `/api/runtime`, `/api/lb`, `/api/routing`, `/api/telemetry`, `/api/logs/*`, `/api/claims`, `/api/events` | Inspect state and history |
| administration | `/api/teams`, `/api/admin/teams`, `/api/admin/public/config`, `/api/admin/public/notifications` | Manage teams and participant-board content |

### Frontend Templates

The frontend is intentionally lightweight:

- `templates/dashboard.html` is a single-page admin control surface that fetches multiple API endpoints and exposes rotation, recovery, team admin, routing, telemetry, logs, and participant-board controls.
- `templates/participant.html` is a public board that shows the active series, host/port access window, organizer notices, hard-bound rules, leaderboard, and a cumulative score chart.
- `static/style.css` provides the shared styling.

This means the backend and frontend are tightly coupled but operationally simple: no separate SPA build, no separate frontend service, and no extra persistence layer.

## How The Ruling Engine Sees Challenge Content

The referee does not reason about exploit code, web frameworks, or machine-specific implementation details. It treats each series as a deployment unit with three variants and a known public port set.

From the engine's perspective, the challenge layer contributes only a few things:

- a series number (`H1` to `H8`)
- three variants (`A`, `B`, `C`)
- one compose file per series
- one replicated deployment per node
- a claim file at `/root/king.txt`
- a few invariant operating-system surfaces used for rule enforcement

That abstraction is why the same ruling engine can judge all eight series without custom scorer logic for each machine.

## Detailed Ruling Engine Walkthrough

This section is the core of the repository.

### Engine Responsibilities

The ruling engine is the combination of:

- `app.py` as the API and operator surface
- `scheduler.py` as the stateful runtime and judge
- `poller.py` as the distributed evidence collector
- `scorer.py` as the ownership decision function
- `enforcer.py` as the punishment ladder
- `db.py` as the source of truth

Together they answer five questions repeatedly:

1. what series is supposed to be live right now?
2. are the replicas for that series healthy enough to trust?
3. which team currently owns each variant by quorum?
4. did any team break the hard-bound rules?
5. if the system is unhealthy, can it safely continue, roll back, or recover?

### Internal Control Loop

The engine operates as a long-running control loop with two clocks:

- a poll interval clock
- a rotation interval clock

The poll interval is frequent and adjudicates claims. The rotation interval is coarse and changes the active series.

At boot the service restores persisted state, recreates the recurring poll job, and, if necessary, recreates the pending one-shot rotation job from the stored `next_rotation` timestamp.

### Start-Up Path

When an operator starts the competition:

1. the runtime refuses to start if it is already active or transitional
2. it clears previous scoring/runtime artifacts with `reset_for_new_competition()`
3. it optionally fetches teams from `BACKEND_URL`
4. it refuses to continue if there is no team roster, unless explicitly overridden
5. it marks the competition as `starting`
6. it deploys `H1` to all configured nodes
7. it waits for deployment health to settle
8. it captures fresh baselines for the new series
9. it marks the competition `running`
10. it arms the future rotation job

The startup sequence is therefore both a bootstrap and a safety gate.

### Evidence Collection Model

`poller.py` is the lowest-level ruling component. Its job is to convert the live cluster into a matrix of comparable observations.

For each node host and each variant, it executes a probe script over SSH that:

- finds the right container using `docker compose ps -q`
- enters the container as root
- prints tagged sections for later parsing

The parser then converts the tagged output into a `VariantSnapshot`.

Each snapshot has:

- `node_host`
- `variant`
- `king`
- `king_mtime_epoch`
- `status`
- `sections`
- `checked_at`

The engine expects a full matrix:

- every configured node
- every configured variant

If any matrix entry is missing, the poll is still recorded but scoring is treated as unsafe.

### Snapshot Status Semantics

The runtime distinguishes several meanings:

- `running`: usable for scoring and health checks
- `degraded`: reachable but excluded from scoring because of clock drift
- `failed`: container missing, claim file missing, or parse/probe failure
- `unreachable`: node SSH path failed

This distinction matters because:

- `degraded` does not necessarily block the competition if quorum still exists
- `failed` and `unreachable` directly reduce healthy quorum
- only `running` replicas are eligible to support a claim

### Health Gate Logic

The engine uses two related but different health checks.

Deploy-time health check:

- used when starting, rotating, restarting, or recovering a series
- requires `king.txt` to be reset to `unclaimed`
- requires enough healthy nodes
- requires no missing snapshot pairs

Poll-time health check:

- used during normal competition
- allows ongoing claims
- still requires a complete enough evidence matrix to trust scoring
- skips scoring for a variant if its healthy replica count drops below `MIN_HEALTHY_NODES`

This separation is important. Deployment health answers "is the round safe to expose?" Poll health answers "is this poll trustworthy enough to score?"

### Clock Drift Handling

The engine does not blindly trust timestamps reported by different nodes. It reads `NODE_EPOCH` from each replica and computes a median baseline.

If a node's epoch differs by more than `MAX_CLOCK_DRIFT_SECONDS`:

- that node is marked degraded for the current poll
- it is excluded from scoring
- a warning event is emitted

This is subtle but critical because the scoring rule depends on the earliest accepted `king.txt` mtime. Without drift control, a bad clock could manufacture false precedence.

### Ownership Resolution

Ownership is decided per variant, not per series.

For each variant:

1. filter to `running` snapshots only
2. ignore empty, malformed, or `unclaimed` claims
3. require a valid `king.txt` mtime
4. group remaining snapshots by team name
5. check whether the current authoritative owner still has quorum
6. if yes, preserve that owner
7. otherwise find any team with quorum
8. pick the team whose earliest supporting `king.txt` mtime is smallest
9. break ties by `NODE_PRIORITY`

The result is a `VariantWinner` with:

- winning team
- accepted timestamp
- source node
- supporting node count
- selection reason

### Why Quorum Matters

The engine is not scoring whichever node was compromised first. It is scoring whichever team has replicated and sustained ownership across enough healthy nodes.

That means a single fast compromise on one node is insufficient. A team must establish enough agreement across replicas to be treated as the authoritative owner.

This design makes the game about distributed control rather than a single lucky write.

### Authoritative Ownership And Reconciliation

Once a winner is accepted for a variant:

- `variant_ownership` is updated
- a points event is recorded
- the engine attempts to rewrite any divergent `king.txt` replicas back to the accepted owner

That last step is easy to miss but very important. The system does not only score ownership; it actively converges the replicated state back to the DB-backed authority.

In other words, the database is not just historical. It becomes the reference state for the cluster.

### Claim Observation Trail

Every poll writes `claim_observations`, including losing and invalid states. This has two purposes:

- post-event auditability
- operator debugging during disputes

Each observation stores whether it was selected and why the poll chose or rejected it, such as:

- `earliest_quorum`
- `current_owner_quorum`
- `no_quorum`
- `no_valid_claims`
- `insufficient_healthy_replicas`
- `incomplete_snapshot_matrix`

That makes the ruling engine explainable after the fact.

### Direct Rule Violations

The direct rule layer comes from properties that can be checked immediately during probing.

These include:

- `king_perm_changed`
- `king_owner_changed`
- `king_immutable`
- `king_deleted`
- `king_not_regular`
- `root_dir_perm_changed`
- `cron_king_persistence`
- `watchdog_process`

These are all attempts to make ownership sticky, hidden, or mechanically protected beyond the allowed rules.

The important design point is that these are not inferred from the exploit path. They are inferred from machine state after compromise.

### Baseline Drift Violations

After a clean deployment, the runtime captures a baseline for each node/variant:

- hash of `/etc/shadow`
- hash of `/root/.ssh/authorized_keys`
- normalized iptables signature
- normalized listener/port signature

Later polls compare live state to that baseline. If state diverges, the runtime adds synthetic violations such as:

- `service_ports_changed`
- `iptables_changed`
- `shadow_changed`
- `authkeys_changed`

These are more strategic than the direct checks. They catch persistent sabotage and environment tampering that may not show up as a simple `king.txt` file violation.

### Violation Attribution

The engine still has to answer one hard question: if a violation occurs on a replica, which team should be blamed?

The attribution strategy is:

1. prefer the snapshot's `king` if it is a valid registered team
2. otherwise use the current authoritative owner for that variant
3. otherwise infer from other running replicas if exactly one plausible team remains

If no team can be attributed safely, the violation is not escalated against a team. This is conservative and avoids arbitrary punishment.

### Escalation And Ban Ladder

New violations are deduplicated through `active_violations`. That prevents the same offense from escalating every single poll.

When a new unique active violation appears:

1. `Enforcer.escalate_team()` increments the team's offense count
2. offense 1 -> team becomes `warned`
3. offense 2 -> team becomes `series_banned`
4. offense 3+ -> team becomes `banned`
5. the specific violation is recorded in `violations`
6. matching high-level events are added to `events`

`series_banned` is cleared on successful rotation via `reset_series_bans()`, while `banned` persists.

### Deploy, Rotate, Restart, Recover

These four actions share some machinery but have different intent:

- `start_competition()`: bootstrap from stopped into `H1`
- `rotate_to_series()`: move from one live series to another
- `restart_current_series()`: rebuild the same live series in place
- `recover_current_series()`: repair from paused/faulted state and leave paused

The common deploy primitive is `_deploy_series_or_raise()`:

1. run compose `up -d --force-recreate` on all nodes
2. poll until deploy-time health passes
3. wait one settle interval
4. poll again
5. capture baselines only after the settled state is clean

This is a strong design choice because the baseline is never captured from a half-broken deployment.

### HAProxy As Part Of The Ruling Engine

HAProxy is not merely an ingress router. The runtime actively manages it as part of adjudication:

- active series listeners are set to `ready`
- inactive series listeners are set to `maint`
- during rotation, current series can be set to `drain`

That means exposure and judgement are coupled:

- only the series the runtime believes is active should be reachable
- traffic shaping follows competition state transitions

The `/api/routing` endpoint surfaces this live routing view back to operators.

### Database As The Engine Memory

`db.py` is best understood as engine memory across three time horizons:

- present tense: `competition`, `containers`, `active_violations`
- round state: `variant_ownership`, `baselines`, `claim_observations`
- historical audit: `point_events`, `violations`, `events`, public-board config

Without this DB, the service could not:

- survive restarts
- explain why a score was awarded
- avoid duplicate escalations
- recover safely after a fault
- generate the public leaderboard

### Operator APIs As Control Hooks

The admin API is thin over runtime methods. The important point is that the actual guardrails live in `scheduler.py`, not in the frontend.

For example:

- `/api/resume` only succeeds after validation
- `/api/recover/redeploy` only works from `paused` or `faulted`
- `/api/rotate/skip` still goes through the same guarded rotation flow
- `/api/poll` still respects runtime status

This prevents the dashboard from becoming a bypass around the engine.

### Public Board As A Read-Only Projection

The participant board is downstream of the same DB and runtime state:

- current series comes from `competition`
- leaderboard comes from `teams` and `point_events`
- notices come from `public_notifications`
- host and port ranges come from config plus active listener inference

So the public board is not a separate app with its own logic. It is a projection of the ruling engine's current state.

For the challenge-side attack paths, see [Machine Exploit Paths](../gameplay/machine-exploit-paths.md).
