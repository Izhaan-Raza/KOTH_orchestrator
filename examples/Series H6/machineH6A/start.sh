#!/bin/bash
set -euo pipefail

# Start the NFS stack explicitly so the no_root_squash path is actually reachable.
mkdir -p /run/rpcbind /var/lib/nfs/rpc_pipefs /proc/fs/nfsd
# Exporting the container overlay fails with "does not support NFS export".
# Mount a dedicated tmpfs so the kernel NFS server can export a real filesystem.
mountpoint -q /srv/nfs/share || mount -t tmpfs -o mode=0777,size=16m tmpfs /srv/nfs/share
chmod 777 /srv/nfs/share
mountpoint -q /proc/fs/nfsd || mount -t nfsd nfsd /proc/fs/nfsd
mountpoint -q /var/lib/nfs/rpc_pipefs || mount -t rpc_pipefs sunrpc /var/lib/nfs/rpc_pipefs

# Pin the NFS helper daemons to fixed ports so the referee's service-port
# baseline stays stable across clean restarts and safe captures.
echo 32765 >/proc/sys/fs/nfs/nlm_tcpport || true
echo 32765 >/proc/sys/fs/nfs/nlm_udpport || true

rpcbind -w
exportfs -ra
rpc.statd --no-notify --port 32766 --outgoing-port 32767 &
rpc.mountd --foreground --no-udp --manage-gids --port 32768 &
rpc.nfsd --no-udp --nfs-version 4 8

# Start distccd - listen on all interfaces, no whitelist (vulnerable)
distccd --daemon \
    --allow 0.0.0.0/0 \
    --listen 0.0.0.0 \
    --port 3632 \
    --log-stderr \
    --verbose \
    --no-detach &

echo "[H6A] distccd running on :3632 (CVE-2004-2687)"
echo "[H6A] NFS share at /srv/nfs/share with no_root_squash"

exec tail -f /dev/null
