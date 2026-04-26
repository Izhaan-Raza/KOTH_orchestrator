#!/bin/bash
# Start SSH
service ssh start

# Start SNMPd with public community
snmpd -C -c /etc/snmp/snmpd.conf -Lo -f &

# Leak the SSH credential in a process list that SNMP exposes.
bash -c 'exec -a "backup-sync --user opsuser --pass snmpops" sleep 999999' &

# Start a root tmux session on a shared socket so a local foothold can hijack it.
tmux -S /tmp/koth-root.sock new-session -d -s root_session -x 220 -y 50
chmod 666 /tmp/koth-root.sock
tmux -S /tmp/koth-root.sock send-keys -t root_session "echo 'Root tmux session active. King file: /root/king.txt'" Enter
tmux -S /tmp/koth-root.sock send-keys -t root_session "while true; do echo '[root@koth] # '; sleep 30; done" Enter

echo "[H7A] SNMP running on :161/udp (public community)"
echo "[H7A] Root tmux session active: tmux -S /tmp/koth-root.sock attach -t root_session"
echo "[H7A] SSH running on :22"

# Keep the container alive even if one backgrounded service exits.
exec tail -f /dev/null
