# Production Remediation Design

## Purpose

This document turns the audit findings into a concrete remediation design for the distributed referee runtime.

It is written against the current implemented architecture:

- One referee process owns the control plane and scoreboard.
- Three challenge nodes host the active series.
- HAProxy fronts player traffic across those nodes.
- The referee reaches nodes over SSH and persists state in SQLite.

The goal is to make that architecture safe enough for an 8-hour live event without relying on hidden operator assumptions.

## Non-Negotiable Invariants

The remediated system must preserve these invariants:

1. `paused` means no scoring and no rotation.
2. Points are awarded only when the referee has enough healthy evidence to trust ownership.
3. Rotation never commits a new series until that series is proven healthy.
4. A failed rotation cannot silently leave the event in a mixed or partially deployed `running` state.
5. A referee restart reconstructs the intended runtime behavior from persisted state.
6. Missing probe data is treated as failure, not ignored.
7. The production runtime model is singular and documented once.

## Root Architectural Correction

## Problem

The current scoring logic assumes each variant (`A`, `B`, `C`) is replicated across three nodes and that the earliest `king.txt` change across those nodes identifies one legitimate winner.

That assumption is not true in the current deployment artifacts. Each node runs its own local container and there is no cross-node replication or shared `king.txt` state.

## Recommended Direction

Do not keep the current "earliest local file mtime across three independent nodes" model.

Use one of these two valid models and make the whole system consistent with it:

### Model A: Centralized Authoritative Ownership (Recommended)

- The referee is the authority for accepted ownership.
- Nodes are execution surfaces only.
- Team claims are still written locally into `king.txt`, but those local files are treated as observations, not truth.
- The referee accepts a winner only when quorum is met.
- After accepting a winner, the referee writes the authoritative owner back to all healthy nodes for that variant.

This model fits the existing centralized referee architecture and avoids pretending that independent node-local files are already replicated state.

### Model B: Independent Node Scoring

- Score each `node + variant` independently.
- Drop the notion that one variant has one winner across the cluster.
- Update point math, UI, runbooks, and event design accordingly.

This is simpler technically, but it changes the game design. If the competition is meant to present replicated services behind a load balancer, Model A is the correct fit.

## Recommendation

Implement Model A.

That means:

- Keep per-variant scoring.
- Require quorum before accepting any ownership change.
- Persist the accepted owner and acceptance timestamp centrally.
- Push the accepted owner to healthy replicas.

This preserves the intended "one winner per variant" competition model and makes the central referee explicitly responsible for it.

## Runtime State Machine

Replace the current implicit state handling with an explicit competition state machine.

## Competition States

- `stopped`
- `starting`
- `running`
- `paused`
- `rotating`
- `faulted`
- `stopping`

## Allowed Transitions

1. `stopped -> starting`
   - Trigger: `/api/competition/start`
   - Preconditions:
     - runtime config valid
     - team roster available
     - no conflicting active lifecycle job

2. `starting -> running`
   - Trigger: H1 deploy succeeds and health gate passes

3. `starting -> faulted`
   - Trigger: H1 deploy fails and rollback cannot restore clean stopped state

4. `starting -> stopped`
   - Trigger: H1 deploy fails but rollback completes cleanly

5. `running -> paused`
   - Trigger: `/api/pause`

6. `paused -> running`
   - Trigger: `/api/resume`
   - Preconditions:
     - current series revalidated
     - quorum healthy
     - no unresolved deploy fault

7. `running -> rotating`
   - Trigger: scheduled or manual rotate

8. `rotating -> running`
   - Trigger: target series deploy succeeds and health gate passes

9. `rotating -> faulted`
   - Trigger: target deploy fails and rollback to previous known-good series also fails

10. `rotating -> running` on previous series
    - Trigger: target deploy fails but rollback to previous series succeeds

11. `running -> stopping`
    - Trigger: `/api/competition/stop`

12. `stopping -> stopped`
    - Trigger: final poll and teardown complete

13. `faulted -> paused`
    - Trigger: operator acknowledges incident after successful manual recovery validation

14. `paused -> faulted`
    - Trigger: explicit validation failure during resume/recovery

## State Semantics

- `paused`: event intentionally halted, no points, no rotation, cluster expected to remain in a validated series state.
- `faulted`: event safety barrier. No scoring, no rotation, no blind resume. Operator must run an explicit recovery flow.
- `rotating`: scoring disabled for the duration of deploy/cutover.

## Persisted Lifecycle Fields

Add or normalize these persisted competition fields:

- `status`
- `current_series`
- `previous_series`
- `poll_cycle`
- `started_at`
- `paused_at`
- `next_rotation_at`
- `rotation_started_at`
- `fault_reason`
- `last_validated_series`
- `last_validated_at`

## Rotation and Recovery Protocol

## Current Unsafe Behavior

Today the runtime tears down the current series first, then attempts the target deploy, and on failure leaves state advanced to the failed target.

That must be replaced.

## Safe Rotation Protocol

For `Hn -> Hn+1`:

1. Acquire lifecycle lock.
2. Verify current state is `running`.
3. Set state to `rotating`.
4. Run one final scoring poll for `Hn`, with normal quorum enforcement.
5. Mark `previous_series = Hn`, `target_series = Hn+1`.
6. Deploy `Hn+1` on all nodes without yet committing `current_series`.
7. Probe all expected `host x variant` snapshots.
8. Require:
   - complete snapshot matrix
   - all required variants present
   - quorum healthy
   - `king.txt=unclaimed` or other centrally defined clean initial owner
   - baseline capture succeeds
9. If target validation passes:
   - tear down `Hn`
   - set `current_series = Hn+1`
   - clear `previous_series`
   - set `status = running`
   - set next absolute rotation time
10. If target validation fails:
   - tear down partial `Hn+1`
   - redeploy `Hn`
   - validate `Hn`
   - if rollback validation succeeds:
     - set `status = paused`
     - keep `current_series = Hn`
     - record `fault_reason`
   - if rollback validation fails:
     - set `status = faulted`
     - keep explicit fault detail

## Why This Works

It prevents the system from ever claiming "we are on Hn+1 and running" before Hn+1 is actually valid.

## Restart Current Series Protocol

`restart_current_series` should use the same machinery as rotation, except target and previous series are the same logical series.

Required behavior:

1. Set `status = rotating`.
2. Redeploy the current series.
3. Revalidate health and recapture baselines.
4. Return to `running` only on success.
5. Enter `paused` or `faulted` on failure.

No special-case fast path should exist.

## Resume Protocol

`resume` must not be a blind state flip.

Required behavior:

1. Allowed only from `paused`.
2. Revalidate the currently recorded `current_series`.
3. Require:
   - complete snapshot matrix
   - quorum healthy
   - no outstanding deploy fault
4. Only then set `status = running` and schedule the next absolute rotation time.

If validation fails, transition to `faulted`.

## Scoring Design

## Poll Gating

Scoring must run only when:

- `status == running`
- `current_series > 0`
- lifecycle operation not in progress

If the system is `paused`, `rotating`, `faulted`, `starting`, or `stopping`, `poll_once()` may collect health data but must not award points.

## Quorum Enforcement

Add quorum enforcement to each scoring cycle.

Recommended rule:

- For each variant, require at least `MIN_HEALTHY_NODES` healthy replicas with complete probe data.
- If a variant does not meet quorum, do not score that variant for that cycle.
- If no variants meet quorum, the cycle records a critical health event and awards no points.

This is stricter and safer than using quorum only at deploy time.

## Winner Resolution for Model A

For each variant:

1. Collect healthy observations.
2. Filter invalid claims.
3. If quorum not met, skip.
4. If all quorum members report the same valid owner, accept immediately.
5. If quorum members disagree:
   - compare `mtime`
   - choose the earliest valid change
   - require that the chosen claim appears on at least quorum-many healthy replicas within a bounded acceptance window
6. Persist the accepted authoritative owner.
7. Push that authoritative owner to all healthy replicas.

This removes the unsafe assumption that one node's earliest local file write is automatically cluster truth.

## Accepted Ownership Persistence

Add a central table for accepted ownership:

### `variant_ownership`

- `series INTEGER NOT NULL`
- `variant TEXT NOT NULL`
- `owner_team TEXT`
- `accepted_mtime_epoch INTEGER`
- `accepted_at TEXT NOT NULL`
- `source_node_host TEXT`
- `evidence_json TEXT`
- `PRIMARY KEY (series, variant)`

This is the authoritative current score state for each variant.

## Probe Completeness and Data Integrity

## Current Problem

Partial probe output is silently accepted.

## Required Rule

Every probe cycle must produce one snapshot for every expected `node_host x variant`.

Expected cardinality:

- `len(node_hosts) * len(variants)`

If a host returns partial output:

- synthesize the missing variants as `failed`
- attach the host stderr/raw output
- count those variants as unhealthy

If an SSH command exits non-zero:

- do not trust the partial success unless the snapshot matrix is complete and internally valid

## Baseline Rules

Baselines must be series-specific and captured only after a series is validated.

Baselines must never be refreshed on:

- a failed deploy
- a failed restart
- a partial probe
- a faulted series

## Database Changes

## Existing Tables to Extend

### `competition`

Add:

- `previous_series INTEGER`
- `paused_at TEXT`
- `rotation_started_at TEXT`
- `fault_reason TEXT`
- `last_validated_series INTEGER`
- `last_validated_at TEXT`

### `containers`

Normalize status semantics:

- `running`
- `degraded`
- `failed`
- `unreachable`
- `rotating`
- `stopped`

Add:

- `expected_series INTEGER`
- `probe_error TEXT`

## New Tables

### `variant_ownership`

Described above.

### `lifecycle_actions`

Tracks operator and scheduler actions for auditability.

Columns:

- `id INTEGER PRIMARY KEY`
- `action_type TEXT NOT NULL`
- `requested_by TEXT`
- `requested_at TEXT NOT NULL`
- `started_at TEXT`
- `completed_at TEXT`
- `status TEXT NOT NULL`
- `source_series INTEGER`
- `target_series INTEGER`
- `detail TEXT`

### `node_health_cycles`

Tracks per-cycle quorum and health facts.

Columns:

- `id INTEGER PRIMARY KEY`
- `poll_cycle INTEGER NOT NULL`
- `series INTEGER NOT NULL`
- `healthy_nodes INTEGER NOT NULL`
- `healthy_variants_json TEXT NOT NULL`
- `degraded_nodes_json TEXT NOT NULL`
- `quorum_met INTEGER NOT NULL`
- `created_at TEXT NOT NULL`

## API and Admin Surface Changes

## Existing Endpoints to Change

### `/api/pause`

- Must pause scoring and rotation.
- Response should include resulting state and whether scoring is halted.

### `/api/resume`

- Must perform validation before returning success.
- On failed validation, return `409` and leave state `faulted` or `paused`.

### `/api/rotate`

- Must return a lifecycle action result, not just `{ok: true}`.
- Include source series, target series, and whether rollback was needed.

### `/api/rotate/restart`

- Must use the safe restart path.

## New Endpoints

### `/api/recover/validate`

- Revalidates the current series without scoring.
- Returns full health and quorum outcome.

### `/api/recover/redeploy`

- Explicit recovery action for a paused or faulted series.
- Runs redeploy plus validation.

### `/api/runtime`

- Returns lifecycle state, active jobs, next rotation absolute time, last validation result, and fault reason.

This is needed because `/api/status` is too shallow for incident handling.

## Scheduler Design

## Current Problem

Only the poll job is recreated on startup, and rotation uses an interval job relative to process start.

## Required Behavior

On startup:

1. Load persisted competition state.
2. Restore poll job if state is not `stopped`.
3. Restore rotation as a one-shot absolute-time job if state is `running` and `next_rotation_at` is present.
4. Do not schedule rotation if state is `paused`, `faulted`, `rotating`, `starting`, or `stopping`.

## Job Model

- Poll job: interval job, but scoring gated by persisted state.
- Rotation job: one-shot absolute job at `next_rotation_at`.
- Lifecycle operations: serialized under one runtime lock and one persisted lifecycle-action record.

This ensures restart recovery uses persisted intent rather than relative wall clock since process boot.

## Production Control Plane Cleanup

The repository must present one production control plane only.

## Required Repo Cleanup

### Keep as production

- `referee-server/`
- distributed node layout under `h1..h8`
- `qa/deployment/*`
- `docs/full-deployment-runbook.md`

### Demote to local-dev only

- root `docker-compose.yml`
- `rotate.sh`

They should be:

- moved under `dev/` or clearly labeled local-only
- removed from production runbooks
- excluded from any "authoritative runtime" wording

## File-by-File Change Plan

## `referee-server/db.py`

Change:

- add schema migration support, not just `CREATE TABLE IF NOT EXISTS`
- extend `competition`
- add `variant_ownership`
- add `lifecycle_actions`
- add `node_health_cycles`
- add helpers:
  - `begin_lifecycle_action(...)`
  - `complete_lifecycle_action(...)`
  - `record_node_health_cycle(...)`
  - `set_variant_owner(...)`
  - `get_variant_owner(...)`

Why:

- current DB can store points and events, but it cannot represent lifecycle intent or authoritative ownership cleanly.

## `referee-server/models.py`

Change:

- expand competition status enum to include:
  - `starting`
  - `rotating`
  - `faulted`
  - `stopping`
- add response models for:
  - runtime detail
  - recovery validation result
  - lifecycle action result

Why:

- current API models cannot faithfully express real state transitions.

## `referee-server/app.py`

Change:

- make admin endpoints return structured lifecycle outcomes
- add `/api/runtime`
- add `/api/recover/validate`
- add `/api/recover/redeploy`
- preserve `409` behavior for guarded failures

Why:

- operators need actionable runtime state and recovery APIs, not just `{ok: true}`.

## `referee-server/poller.py`

Change:

- enforce complete expected snapshot matrix
- synthesize missing variants on partial output
- distinguish:
  - `failed`
  - `unreachable`
  - `partial`
- return cycle health metadata in addition to snapshots and violations

Why:

- missing evidence must become explicit degraded input, not silent omission.

## `referee-server/scorer.py`

Change:

- remove direct dependence on raw earliest local file winner as final truth
- implement quorum-aware winner resolution over healthy observations
- emit both:
  - `candidate winner`
  - `acceptance confidence / quorum status`

Why:

- scoring must align with the centralized authoritative ownership model.

## `referee-server/scheduler.py`

Change:

- implement explicit lifecycle state machine
- gate scoring on `running`
- restore jobs from DB on startup
- replace interval-based rotation scheduling with absolute-time scheduling
- replace fail-forward rotation with validated deploy plus rollback
- route `restart_current_series` through the same safe deploy path
- make `resume` validate before returning to `running`

Why:

- this is the core control-plane fix.

## `referee-server/setup_cli.py`

Change:

- add a stronger preflight:
  - runtime config valid
  - node reachability
  - expected series directories present
  - expected compose services present
  - complete probe matrix for a test series

Why:

- setup validation should exercise the actual assumptions the referee needs in production.

## `qa/deployment/validate_referee_lb.sh`

Change:

- validate explicit production config source
- verify that referee runtime reports the expected state model
- add an optional dry-run mode that exercises:
  - start
  - pause
  - resume
  - rotate
  - stop

Why:

- current validation proves installation, not safe lifecycle behavior.

## `qa/deployment/validate_koth_node.sh`

Change:

- validate per-series compose service names
- validate probe completeness for the active series
- verify that the expected `king.txt` initialization exists after bring-up

Why:

- node validation should support health-gated deploy assumptions.

## `README.md`

Change:

- stop calling root compose authoritative
- explicitly state the production model is referee-managed distributed deployment
- link to the production runbook and this remediation design

Why:

- eliminate control-plane ambiguity.

## `docs/full-deployment-runbook.md`

Change:

- document the new lifecycle states
- document recovery flows separately from pause/resume
- document authoritative ownership semantics
- document restart behavior and expected recovery checks

Why:

- operators need the real runtime model, not a simplified one.

## `docker-compose.yml` and `rotate.sh`

Change:

- relabel as local dev only, or move out of root-level authoritative paths

Why:

- prevent accidental production use.

## Test Plan

## Unit Tests

Add to `referee-server/tests/`:

1. `test_pause_blocks_scoring`
2. `test_quorum_loss_blocks_variant_scoring`
3. `test_restart_restores_rotation_job_from_db`
4. `test_partial_probe_generates_missing_variant_failures`
5. `test_failed_rotation_rolls_back_to_previous_series`
6. `test_resume_requires_revalidation`
7. `test_restart_current_series_uses_health_gate`
8. `test_faulted_state_blocks_resume`
9. `test_rotation_uses_absolute_next_rotation_time`
10. `test_authoritative_owner_persisted_per_variant`

## Integration Tests

Create an integration harness that uses mocked SSH responses and a temp SQLite DB.

Scenarios:

1. `start -> running`
2. `start` with no teams -> reject
3. `running -> pause -> poll -> no points added`
4. `running -> quorum loss -> no points`
5. `running -> rotate success -> running on next series`
6. `running -> rotate target fails -> rollback to previous series`
7. `running -> rotate target fails and rollback fails -> faulted`
8. `paused -> resume with healthy series -> running`
9. `paused -> resume with invalid series -> faulted`
10. `restart while running -> jobs restored correctly`

## Deployment Validation Tests

The deployment scripts should gain an optional live dry-run workflow:

1. start event
2. verify `/api/runtime` shows `running`
3. force pause
4. verify no point movement across one poll interval
5. force resume
6. rotate
7. verify `current_series` changed only after successful validation
8. stop

## Observability Requirements

Add operator-visible signals for:

- current lifecycle state
- fault reason
- last validated series
- last successful poll time
- healthy nodes count
- per-variant quorum status
- next absolute rotation time
- active scheduler jobs

Without these, the system can still look healthy while being invalid.

## Migration Order

Implement in this order:

1. Introduce explicit state model and DB migration support.
2. Gate polling and scoring on `running`.
3. Add quorum enforcement to poll cycles.
4. Enforce complete probe matrix.
5. Rework rotation and restart flows to validate before commit.
6. Restore scheduler state from DB on startup.
7. Add recovery endpoints and runtime introspection.
8. Clean up docs and retire the local-production ambiguity.
9. Add dry-run validation automation.

## Live Event Go/No-Go Criteria After Remediation

Do not sign off until all are true:

1. Pause demonstrably freezes scoring.
2. One-node and two-node outage scenarios demonstrably do not award points below quorum.
3. Failed rotation demonstrably rolls back or enters `faulted`, never silent `running`.
4. Referee restart demonstrably preserves rotation timing.
5. Partial probe output demonstrably marks missing variants failed.
6. The documented production flow no longer references the local root compose runtime as authoritative.
