#!/bin/bash
set -euo pipefail

mkdir -p /data/db /var/log

service ssh start

# Start MongoDB without auth and seed it deterministically.
mongod --bind_ip_all --port 27017 --dbpath /data/db --logpath /var/log/mongodb.log --fork

for _ in $(seq 1 30); do
    if mongo --quiet --eval "db.adminCommand({ ping: 1 }).ok" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

mongo kothdb /seed.js >/dev/null 2>&1 || true

echo "[H6B] MongoDB running on :27017 (no auth)"
echo "[H6B] SSH running on :22 for cracked credential reuse"
echo "[H6B] PrivEsc: mongouser is in docker group"

exec tail -f /var/log/mongodb.log
