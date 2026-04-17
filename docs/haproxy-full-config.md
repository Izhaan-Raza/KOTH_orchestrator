# Full HAProxy Config (All TCP Game Ports)

Use this file as a copy-ready `/etc/haproxy/haproxy.cfg` for your current node mapping:

- `n1 = 192.168.0.70`
- `n2 = 192.168.0.103`
- `n3 = 192.168.0.106`

Exact listener and service names to maintain on the router page / HAProxy config:

| Listener / Router Entry | Challenge Service | Public Port |
|---|---|---:|
| `p10001` | `machineH1A` | `10001` |
| `p10002` | `machineH1B` Redis | `10002` |
| `p10003` | `machineH1B` SSH | `10003` |
| `p10004` | `machineH1C` | `10004` |
| `p10010` | `machineH2A` | `10010` |
| `p10011` | `machineH2B` | `10011` |
| `p10012` | `machineH2C` | `10012` |
| `p10020` | `machineH3A` SMB | `10020` |
| `p10021` | `machineH3A` SSH | `10021` |
| `p10022` | `machineH3B` | `10022` |
| `p10023` | `machineH3C` | `10023` |
| `p10030` | `machineH4A` | `10030` |
| `p10031` | `machineH4B` | `10031` |
| `p10032` | `machineH4C` | `10032` |
| `p10040` | `machineH5A` | `10040` |
| `p10041` | `machineH5B` | `10041` |
| `p10042` | `machineH5C` | `10042` |
| `p10050` | `machineH6A` distcc | `10050` |
| `p10051` | `machineH6A` NFS | `10051` |
| `p10052` | `machineH6B` MongoDB | `10052` |
| `p10053` | `machineH6C` HTTPS | `10053` |
| `p10054` | `machineH6B` SSH | `10054` |
| `p10055` | `machineH6C` SSH | `10055` |
| `p10061` | `machineH7A` SSH | `10061` |
| `p10062` | `machineH7B` | `10062` |
| `p10063` | `machineH7C` | `10063` |
| `p10070` | `machineH8A` | `10070` |
| `p10071` | `machineH8B` | `10071` |
| `p10072` | `machineH8C` | `10072` |

When editing the router page, update the backend server rows inside these exact listener entries. Do not rename the listener names unless you are updating the HAProxy file, validator expectations, and LB dashboard together.

```cfg
global
    log /dev/log local0
    log /dev/log local1 notice
    daemon
    user haproxy
    group haproxy
    maxconn 4096

defaults
    log global
    mode tcp
    option tcplog
    timeout connect 5s
    timeout client 2m
    timeout server 2m

listen p10001
    bind *:10001
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10001 check
    server n2 192.168.0.103:10001 check
    server n3 192.168.0.106:10001 check

listen p10002
    bind *:10002
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10002 check
    server n2 192.168.0.103:10002 check
    server n3 192.168.0.106:10002 check

listen p10003
    bind *:10003
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10003 check
    server n2 192.168.0.103:10003 check
    server n3 192.168.0.106:10003 check

listen p10004
    bind *:10004
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10004 check
    server n2 192.168.0.103:10004 check
    server n3 192.168.0.106:10004 check

listen p10010
    bind *:10010
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10010 check
    server n2 192.168.0.103:10010 check
    server n3 192.168.0.106:10010 check

listen p10011
    bind *:10011
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10011 check
    server n2 192.168.0.103:10011 check
    server n3 192.168.0.106:10011 check

listen p10012
    bind *:10012
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10012 check
    server n2 192.168.0.103:10012 check
    server n3 192.168.0.106:10012 check

listen p10020
    bind *:10020
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10020 check
    server n2 192.168.0.103:10020 check
    server n3 192.168.0.106:10020 check

listen p10021
    bind *:10021
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10021 check
    server n2 192.168.0.103:10021 check
    server n3 192.168.0.106:10021 check

listen p10022
    bind *:10022
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10022 check
    server n2 192.168.0.103:10022 check
    server n3 192.168.0.106:10022 check

listen p10023
    bind *:10023
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10023 check
    server n2 192.168.0.103:10023 check
    server n3 192.168.0.106:10023 check

listen p10030
    bind *:10030
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10030 check
    server n2 192.168.0.103:10030 check
    server n3 192.168.0.106:10030 check

listen p10031
    bind *:10031
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10031 check
    server n2 192.168.0.103:10031 check
    server n3 192.168.0.106:10031 check

listen p10032
    bind *:10032
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10032 check
    server n2 192.168.0.103:10032 check
    server n3 192.168.0.106:10032 check

listen p10040
    bind *:10040
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10040 check
    server n2 192.168.0.103:10040 check
    server n3 192.168.0.106:10040 check

listen p10041
    bind *:10041
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10041 check
    server n2 192.168.0.103:10041 check
    server n3 192.168.0.106:10041 check

listen p10042
    bind *:10042
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10042 check
    server n2 192.168.0.103:10042 check
    server n3 192.168.0.106:10042 check

listen p10050
    bind *:10050
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10050 check
    server n2 192.168.0.103:10050 check
    server n3 192.168.0.106:10050 check

listen p10051
    bind *:10051
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10051 check
    server n2 192.168.0.103:10051 check
    server n3 192.168.0.106:10051 check

listen p10052
    bind *:10052
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10052 check
    server n2 192.168.0.103:10052 check
    server n3 192.168.0.106:10052 check

listen p10053
    bind *:10053
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10053 check
    server n2 192.168.0.103:10053 check
    server n3 192.168.0.106:10053 check

listen p10054
    bind *:10054
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10054 check
    server n2 192.168.0.103:10054 check
    server n3 192.168.0.106:10054 check

listen p10055
    bind *:10055
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10055 check
    server n2 192.168.0.103:10055 check
    server n3 192.168.0.106:10055 check

listen p10061
    bind *:10061
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10061 check
    server n2 192.168.0.103:10061 check
    server n3 192.168.0.106:10061 check

listen p10062
    bind *:10062
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10062 check
    server n2 192.168.0.103:10062 check
    server n3 192.168.0.106:10062 check

listen p10063
    bind *:10063
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10063 check
    server n2 192.168.0.103:10063 check
    server n3 192.168.0.106:10063 check

listen p10070
    bind *:10070
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10070 check
    server n2 192.168.0.103:10070 check
    server n3 192.168.0.106:10070 check

listen p10071
    bind *:10071
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10071 check
    server n2 192.168.0.103:10071 check
    server n3 192.168.0.106:10071 check

listen p10072
    bind *:10072
    balance roundrobin
    option tcp-check
    server n1 192.168.0.70:10072 check
    server n2 192.168.0.103:10072 check
    server n3 192.168.0.106:10072 check
```

Apply and validate:

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
sudo systemctl restart haproxy
```

If the node IPs rotate, update every backend `server n1/n2/n3` entry in `/etc/haproxy/haproxy.cfg`, validate the file, and then restart HAProxy:

```bash
sudo editor /etc/haproxy/haproxy.cfg
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
sudo systemctl restart haproxy
sudo systemctl --no-pager --full status haproxy
```

For the current deployment, the backend mapping must be:

- `n1 = 192.168.0.70`
- `n2 = 192.168.0.103`
- `n3 = 192.168.0.106`

That means each listener above must keep the same public port and service name, but the three backend rows under it must point at:

- `server n1 192.168.0.70:<same port> check`
- `server n2 192.168.0.103:<same port> check`
- `server n3 192.168.0.106:<same port> check`

Note: `10060` is UDP (`161/udp`) and is not included in this TCP config.
