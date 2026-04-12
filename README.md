=
# Will Update the new orchestrator and refree system flow soon



# Refer to H1 serires docs for more clarity

## 🧩 Machine Matrix

| Machine   | Port Config | Initial Vector                              | PrivEsc Vector                             |
|-----------|-------------|---------------------------------------------|--------------------------------------------|
| machineH1A | 10001 | WordPress Plugin RCE (Reflex Gallery)       | SUID `/usr/bin/find`                       |
| machineH1B | 10002 | Redis Unauthenticated                       | Write SSH key to `/root/.ssh/`             |
| machineH1C | 10004 | Anonymous FTP → shell upload to web root   | World-writable root cronjob script         |
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
| machineH6B | 10052 | MongoDB No Auth (crack hashes)            | `mongouser` in `docker` group              |
| machineH6C | 10053 | Heartbleed CVE-2014-0160 (session leak)    | `sudo systemctl` → spawn shell             |
| machineH7A | 10060 | SNMP Public community leaks processes      | Hijack active root `tmux` session          |
| machineH7B | 10062 | Grafana Path Traversal CVE-2021-43798     | `/etc/shadow` is world-writable            |
| machineH7C | 10063 | RSync anonymous write                      | PATH hijacking in root cron (`ls`)         |
| machineH8A | 10070 | PHPMyAdmin root:blank                      | MySQL UDF for command execution            |
| machineH8B | 10071 | Flask/Jinja2 SSTI                          | `/etc/sudoers` is world-writable           |
| machineH8C | 10072 | Laravel Debug CVE-2021-3129               | SUID `/bin/bash_suid` (`bash_suid -p`)     |

---
