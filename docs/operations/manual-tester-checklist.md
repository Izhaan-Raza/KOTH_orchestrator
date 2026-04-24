# Manual Tester Checklist

This runbook is for human testers validating the full 24-problem KOTH event end to end.

Use it when you want:
- a clean manual test cycle across every machine from `H1A` through `H8C`
- parallel solver activity so you can watch points and ownership move in real time
- consistent validation of the dashboard, logs, and scoring after every solve

This checklist assumes the referee was reset to a fresh baseline before the session:
- runtime state: `stopped`
- points, events, claims, and violations cleared
- team roster preserved but reset to `active / 0 offenses / 0 points`

## Scope

- Referee UI: `http://10.42.0.1:8000` or `http://192.168.0.12:8000`
- Challenge traffic enters through the LB and router forwards
- Each series exposes exactly three machine variants: `A`, `B`, `C`
- The referee awards points once per poll cycle based on accepted quorum ownership

## Team Roles

Assign at least these people:

1. `Operator`
   - controls the referee UI
   - rotates series
   - records pass/fail notes

2. `Observer`
   - watches `Operations`, `Routing`, `Health`, and `Logs`
   - confirms scoring and log evidence

3. `Tester Alpha`
   - solves or attacks assigned target

4. `Tester Beta`
   - solves or attacks assigned target

5. `Tester Gamma`
   - solves or attacks assigned target

Optional:

6. `Contention Tester`
   - attempts to steal ownership after the first solve so you can validate ownership transfer

## Before You Start

1. Open the dashboard and enter the operator API key.
2. Confirm `Operations` shows:
   - `Competition = stopped`
   - `Current Series = n/a`
   - leaderboard points all at `0.0`
3. Confirm `Logs` shows:
   - empty or near-empty `Referee Log`
   - empty or near-empty `Claim Trace`
   - no old scoring events in `Recent Events`
4. Confirm `Teams` contains the test teams you plan to use.
   - If needed, create them from the dashboard.
5. Tell every tester their team name before the exercise begins.

## Global Solve Rule

Every tester must follow the same final step after reaching root:

1. Write the exact team name into `/root/king.txt`
2. Read it back immediately to confirm the write
3. Keep the shell/session stable for at least one full poll cycle
   - target: `35-45 seconds`
4. Tell the Observer the exact time they wrote the file

Example final write:

```bash
echo "Team Alpha" > /root/king.txt
cat /root/king.txt
```

## What The Observer Must Validate For Every Solve

For every successful solve, validate all of these:

1. `Operations > Leaderboard`
   - the correct team gets `+1.0`
   - no unexpected ban or offense appears

2. `Operations > Recent Events`
   - one `ownership` event for the accepted winner
   - one `points_awarded` event for that same team / variant

3. `Logs > Claim Trace`
   - the relevant variant shows observed claims
   - one row is selected
   - expected `selection_reason` is visible:
     - `earliest_quorum` for a newly accepted owner
     - `current_owner_quorum` when a current owner keeps control
     - `no_valid_claims` only if nobody actually solved it

4. `Logs > Referee Log`
   - look for `poll_variant_decision`
   - confirm the chosen winner and supporting node count

5. `Routing`
   - all active-series listeners remain `UP`

6. `Health`
   - target replica stays `healthy` / `running`
   - no unexpected restart / OOM / crash appears

## Parallel Solve Pattern Per Series

Do this for every series:

1. Operator sets the target series using `Skip Target`.
2. Operator presses `Validate`.
3. Observer confirms:
   - `Routing` shows exactly the expected ports for the series
   - `Health` shows all 9 replicas present
4. Run the first wave in parallel:
   - Tester Alpha attacks variant `A`
   - Tester Beta attacks variant `B`
   - Tester Gamma attacks variant `C`
5. After all three teams have written `king.txt`, wait one poll cycle and validate scoring.
6. Run the second wave for contention:
   - choose one variant from the same series
   - a second team steals it after the first team already scored
   - wait one more poll cycle
   - validate ownership transfer and the next point
7. Only rotate after both the first-wave solve and the contention exercise are complete.

## Series Checklist

For each row below:
- route the referee to the correct series first
- have the assigned tester exploit the initial vector
- escalate to root with the listed privilege escalation path
- write the team name to `/root/king.txt`
- validate the logs and score before moving on

### H1

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 1 | `H1A` | `10001` | WordPress Reflex Gallery RCE | SUID `/usr/bin/find` | `Claim Trace` shows variant `A`; `points_awarded` for the winning team |
| 2 | `H1B` | `10002` | Unauthenticated Redis | Write SSH key to `/root/.ssh/` | No false `authkeys_changed` ban; score appears cleanly |
| 3 | `H1C` | `10004` | PHP ping command injection | SUID `/usr/local/bin/net-search` | No false `watchdog_process`; score appears once the team owns it |

### H2

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 4 | `H2A` | `10010` | Jenkins Script Console | `sudo python3` | Health remains stable after solve; no deploy-health regression |
| 5 | `H2B` | `10011` | PHP SQLi | MySQL FILE/UDF privileges | `Claim Trace` rows for variant `B` and a clean point event |
| 6 | `H2C` | `10012` | Tomcat default creds | PwnKit | `Routing` stays UP on `10012`; no restart loop appears |

### H3

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 7 | `H3A` | `10020` | SMB anonymous share | `lxd` group breakout | Correct point for variant `A`; no node health alerts |
| 8 | `H3B` | `10022` | Drupalgeddon2 | Writable cron `tar *` | `ownership` then `points_awarded` for variant `B` |
| 9 | `H3C` | `10023` | Exposed `.git` | `perl` with `cap_setuid` | `Health` still shows replicas stable after takeover |

### H4

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 10 | `H4A` | `10030` | Node deserialization | Password in `/var/backups` | `Routing` on `10030` remains stable throughout |
| 11 | `H4B` | `10031` | Spring4Shell | Root password in `.bash_history` | `Claim Trace` selected row should match the scorer winner |
| 12 | `H4C` | `10032` | SSRF to internal Node API | Internal root API exec | No unexpected crash or unhealthy container after exploitation |

### H5

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 13 | `H5A` | `10040` | Webmin RCE | Drops directly to root | First-wave score should appear within one poll cycle |
| 14 | `H5B` | `10041` | ElasticSearch scripting RCE | `www-data` can write `/etc/passwd` | `Events` show only intended scoring and no false violation |
| 15 | `H5C` | `10042` | Apache Struts 2017-5638 | `LD_PRELOAD` sudo path | `Routing` and `Health` stay green on active ports |

### H6

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 16 | `H6A` | `10050` | distcc | NFS `no_root_squash` | Container stays healthy; no NFS/export health failure |
| 17 | `H6B` | `10052`, `10054` | MongoDB no auth | `docker` group | Score lands on variant `B` and health remains stable |
| 18 | `H6C` | `10053`, `10055` | Heartbleed | `sudo systemctl start <unit>` | `Events` show scoring only, no restart churn |

### H7

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 19 | `H7A` | `10060`, `10061` | SNMP public community | Hijack root `tmux` | Score the variant without LB/health regression |
| 20 | `H7B` | `10062` | Grafana traversal/admin exec | World-writable `/etc/shadow` | No false `shadow_changed` ban; clean scoring only |
| 21 | `H7C` | `10063` | RSync anonymous write | PATH hijack in root cron | `Claim Trace` and `Events` agree on the winner |

### H8

| Step | Machine | Port(s) | Initial Vector | PrivEsc | Expected UI / Log Validation |
|---|---|---:|---|---|---|
| 22 | `H8A` | `10070` | PHPMyAdmin root:blank | MySQL UDF shell | Point appears for variant `A`; no crash |
| 23 | `H8B` | `10071` | Flask/Jinja2 SSTI | Writable sudoers trick | `Health` remains normal while score increments |
| 24 | `H8C` | `10072` | Laravel debug RCE | SUID `bash_suid -p` | `points_awarded` and selected claim are both present |

## Contention Exercise Per Series

After the first solver on a chosen variant gets a point:

1. A second team attacks the same variant.
2. That second team reaches root and overwrites `/root/king.txt` with its own team name.
3. Wait one poll cycle.
4. Observer validates:
   - the second team receives the next point
   - `Claim Trace` shows the second team selected
   - `selection_reason` is appropriate for the takeover
   - no duplicate point event is created in the same cycle

## Failure Conditions

Stop the session and record a bug if any of these happen:

1. Team writes the correct `king.txt` value and no score appears after one poll cycle.
2. Wrong team is selected in `Claim Trace`.
3. `Events` show `points_awarded` without a matching claim.
4. A team is warned / series-banned / banned without an actual prohibited persistence action.
5. Active listener shows `DOWN` or no backend for the live series while the target is supposed to be up.
6. Container telemetry shows repeated restarts, OOM, or unhealthy state after a simple solve.
7. Dashboard tab data disagrees with itself:
   - leaderboard changed but no point event
   - claim trace selected one team but events awarded another

## Final Signoff

At the end of the full 24-box run, confirm:

1. Every machine was solved at least once.
2. Every series was rotated intentionally and validated before testing.
3. Every first-wave parallel solve produced the expected points.
4. Every contention exercise transferred ownership correctly.
5. No false bans occurred.
6. No series failed health after a normal solve.
7. Logs, claims, routing, and health all told the same story.
