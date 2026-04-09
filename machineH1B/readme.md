# Machine Operations Guide: [H1B - Redis]

### 🎯 Target Profile

- **OS:** Ubuntu 22.04
- **Service:** Redis / OpenSSH
- **Vulnerabilities:** Unauthenticated Redis ➔ SSH Authorized_Keys Injection
- **Flag Location:** `/root/king.txt`

---

### ⚙️ Automated Lifecycle (The Orchestrator)

During the live event, **do not manually start or stop this container.** The `rotate.sh` orchestrator automatically builds, boots, and tears down this machine at the designated hour. Port mappings (for both SSH and Redis) will be dynamically assigned and announced to the players by the orchestrator.

### 🚑 Emergency Reset (Manual Override)

If a team irreversibly breaks the machine (e.g., flushes the entire SSH config or crashes the Redis daemon) and you need to reset it mid-round _without_ affecting the other active boxes, run these exact commands from the orchestrator directory:

```bash
# 1. Nuke the broken instance
docker stop [machineH1B] && docker rm [machineH1B]

# 2. Rebuild and deploy a fresh instance (Takes < 5 seconds via cache)
docker-compose build [machineH1B]
docker-compose up -d [machineH1B]
```

### 🚩 Scoring & Flag Rules

- The scoring bot (`koth_bot.py`) reads the flag via the Docker daemon (`docker exec`). It is immune to internal container firewalls or broken SSH keys.
- If the bot stops awarding points for this machine, a player likely changed the flag permissions to lock out other players, inadvertently locking out the bot.
- **Hot-Fix:** Run `docker exec [machineH1B] chmod 644 /root/king.txt` to restore bot access.

### 🧠 Expected Player Behavior

- **"SSH is asking for a password, but I don't have one!"**
  - **Cause:** Password authentication is intentionally disabled (`PasswordAuthentication no`).
  - **Action:** Do nothing. Players are supposed to bypass passwords entirely by injecting their own public key via the Redis database save exploit.
- **"Redis is giving me an error when I try to save!"**
  - **Cause:** They are likely trying to save the DB file to a directory that Redis doesn't have permissions for, or using the wrong `CONFIG SET` syntax.
  - **Action:** Do nothing. The vulnerability is functional; their syntax is just flawed.
