# KoTH Orchestrator

## Operational Model

- Production runtime is the distributed referee-managed model under `referee-server/` plus node-local `h1..h8` directories on `node1/node2/node3`.
- `Series HN/docker-compose.yml` files are the per-series deploy artifacts copied into node-local `hN/` directories and validated by the referee before a series becomes active.
- Root-level `docker-compose.yml` and `rotate.sh` are local/dev-only artifacts and must not be treated as the production control plane.
- Operators should use `/api/runtime`, `/api/recover/validate`, and `/api/recover/redeploy` for runtime inspection and recovery.
- The dashboard now includes admin team controls: create teams, manually ban a team, and manually unban a team. New team names must satisfy the same claim rules as `king.txt` ownership, so reserved or malformed names such as `unclaimed` are rejected.
- The public participant board on `:9000` now shows the current access window, organizer notices, hard-bound rules, a live leaderboard, and a cumulative score graph for the leading teams.
- The admin dashboard on `:8000` now renders the full team table instead of truncating to the first 25 teams.
- Manual test execution guide: [docs/manual-tester-checklist.md](docs/manual-tester-checklist.md)
- Referee rule validation guide: [docs/referee-rule-validation-checklist.md](docs/referee-rule-validation-checklist.md)
- Separate attacker-style Codex prompt: [docs/codex-h1a-player-prompt.md](docs/codex-h1a-player-prompt.md)

## 🧩 Machine Matrix

| Machine   | Port Config | Initial Vector                              | PrivEsc Vector                             |
|-----------|-------------|---------------------------------------------|--------------------------------------------|
| machineH1A | 10001 | WordPress Plugin RCE (Reflex Gallery)       | SUID `/usr/bin/find`                       |
| machineH1B | 10002 | Redis Unauthenticated                       | Write SSH key to `/root/.ssh/`             |
| machineH1C | 10004 | Ping command injection in PHP diagnostics  | SUID `/usr/local/bin/net-search`           |
| machineH2A | 10010 | Jenkins Script Console (no auth)           | `sudo python3` (no password)               |
| machineH2B | 10011 | PHP SQL Injection                           | MySQL root with FILE/UDF privileges        |
| machineH2C | 10012 | Tomcat default creds `tomcat:tomcat`        | PwnKit CVE-2021-4034                       |
| machineH3A | 10020 | SMB Anonymous share leaks SSH key          | User in `lxd` group (container breakout)   |
| machineH3B | 10022 | Drupalgeddon2 CVE-2018-7600                | Root cron `tar *` in writable dir          |
| machineH3C | 10023 | Exposed `.git` leaks web creds             | `/usr/bin/perl` has `cap_setuid`           |
| machineH4A | 10030 | Node.js Deserialization (node-serialize)   | Cleartext root pass in `/var/backups/`     |
| machineH4B | 10031 | Spring4Shell CVE-2022-22965                | Root password in `.bash_history`           |
| machineH4C | 10032 | SSRF to internal Node API                  | Internal root API executes commands        |
| machineH5A | 10040 | Webmin RCE CVE-2019-15107                  | Drops directly to root                     |
| machineH5B | 10041 | ElasticSearch Dynamic Scripting RCE        | `www-data` can write `/etc/passwd`         |
| machineH5C | 10042 | Apache Struts CVE-2017-5638               | `sudo` allows `LD_PRELOAD`                 |
| machineH6A | 10050 | distcc CVE-2004-2687                       | NFS `no_root_squash` — write SUID binary   |
| machineH6B | 10052, 10054 | MongoDB No Auth → crack reused SSH creds | `mongouser` in `docker` group         |
| machineH6C | 10053, 10055 | Heartbleed CVE-2014-0160 leaks SSH creds | `sudo /bin/systemctl start <unit>`    |
| machineH7A | 10060, 10061 | SNMP public community leaks SSH creds | Hijack shared root `tmux` socket           |
| machineH7B | 10062 | Grafana traversal → read creds → admin exec | `/etc/shadow` is world-writable         |
| machineH7C | 10063 | RSync anonymous write                      | PATH hijacking in root cron (`ls`)         |
| machineH8A | 10070 | PHPMyAdmin root:blank                      | MySQL UDF → `/usr/local/bin/mysql-root-shell` |
| machineH8B | 10071 | Flask/Jinja2 SSTI                          | Fake `sudo` trusts world-writable sudoers  |
| machineH8C | 10072 | Laravel Debug CVE-2021-3129               | SUID `/bin/bash_suid` (`bash_suid -p`)     |

---

## Referee Server (V2)

- Implementation directory: `referee-server/`
- Runtime loads configuration from process environment first, then `referee-server/.env`.
- Mixed SSH usernames across challenge nodes are supported via optional `NODE_SSH_TARGETS` in `referee-server/.env`.
- Production startup is fail-closed: `ADMIN_API_KEY` must be set unless explicitly overridden with `ALLOW_UNSAFE_NO_ADMIN_API_KEY=true`.
- Competition startup requires a non-empty team roster. Keep an existing `referee.db` team table or configure `BACKEND_URL` to return `/teams`.
- Runtime lifecycle states are explicit: `starting`, `running`, `paused`, `rotating`, `faulted`, `stopping`, `stopped`.
- `paused` means intentionally halted and resumable after validation. `faulted` means unsafe state; use recovery APIs before resuming.
- `/api/recover/validate` now reports both `healthy_nodes` and `total_nodes`; the dashboard displays this as `healthy=X of Y nodes, minimum Z required`.
- `POST /api/competition/stop` stops the competition, not the referee daemon. To stop the actual service, use `sudo systemctl stop koth-referee` on the referee host.
- Start command:

```bash
cd referee-server
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
