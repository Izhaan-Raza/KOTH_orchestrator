# Machine H2A: Jenkins & Python SUID

**Series:** Hour 2
**Port:** 10010
**Difficulty:** Medium (Heavyweight Container)
**Service:** Jenkins LTS (2.235.1) on OpenJDK 11

## 🎯 Overview

H2A simulates a classic CI/CD infrastructure oversight. It features an outdated, unauthenticated Jenkins instance that exposes the Groovy Script Console to the public. Once initial access is gained as the low-privilege `jenkins` user, attackers must leverage a `sudo` misconfiguration allowing passwordless execution of Python 3 to escalate to root.

## 🪲 Vulnerabilities

1. **Unauthenticated Jenkins Script Console:** The setup script (`disable-security.groovy`) explicitly disables Jenkins security and CSRF protection, allowing anyone to execute arbitrary Groovy code on the host.
2. **Sudo Misconfiguration:** The `jenkins` user is granted `NOPASSWD` access to `/usr/bin/python3` in the `/etc/sudoers` file.

## ⚔️ The Kill Chain (Exploit Path)

### 1. Initial Access (RCE)

- Navigate to `http://<TARGET_IP>:10010` in a web browser.
- Go to **Manage Jenkins** -> **Script Console**.
- Verify execution context by running:
  ```groovy
  println "whoami".execute().text
  ```
