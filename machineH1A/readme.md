# Machine Operations Guide: [H1A - WordPress]

### 🎯 Target Profile
* **OS:** Ubuntu 22.04
* **Service:** Apache/PHP (WordPress)
* **Vulnerabilities:** Unauthenticated File Upload (Reflex Gallery) ➔ SUID `find`
* **Flag Location:** `/root/king.txt`

---

### ⚙️ Automated Lifecycle (The Orchestrator)
During the live event, **do not manually start or stop this container.** The `rotate.sh` orchestrator automatically builds, boots, and tears down this machine at the designated hour. Port mappings will be dynamically assigned and announced to the players by the orchestrator.

### 🚑 Emergency Reset (Manual Override)
If a team irreversibly breaks the machine (e.g., deletes the web directory or crashes the database) and you need to reset it mid-round *without* affecting the other active boxes, run these exact commands from the orchestrator directory:

```bash
# 1. Nuke the broken instance
docker stop [machineH1A] && docker rm [machineH1A]

# 2. Rebuild and deploy a fresh instance (Takes < 5 seconds via cache)
docker-compose build [machineH1A]
docker-compose up -d [machineH1A]
```

### 🚩 Scoring & Flag Rules
* The scoring bot (`koth_bot.py`) reads the flag via the Docker daemon (`docker exec`). It is immune to internal container firewalls.
* If the bot stops awarding points for this machine, a player likely changed the flag permissions. 
* **Hot-Fix:** Run `docker exec [machineH1A] chmod 644 /root/king.txt` to restore bot access.