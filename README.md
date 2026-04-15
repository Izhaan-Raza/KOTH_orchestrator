# KoTH Orchestrator

## Operational Model

- `docker-compose.yml` at the repo root is the authoritative competition runtime. `rotate.sh` targets the master service names `machineH{N}{A|B|C}`.
- `Series HN/docker-compose.yml` files are for isolated per-hour build/debug workflows. They use the same service names and image tags as the master stack so there is a single naming model across the repo.
- Do not run a per-series compose stack at the same time as the master stack for the same hour. They intentionally publish the same external competition ports.

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
- Start command:

```bash
cd referee-server
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
