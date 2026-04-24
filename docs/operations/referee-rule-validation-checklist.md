# Referee Rule Validation Checklist

This checklist is for operators validating that normal capture actions stay clean and only referee-prohibited persistence or tamper actions generate warnings or bans.

Use this together with `qa/deployment/validate_rule_matrix_live.py`.

## Scope

- Exhaustive safe-capture validation across all `H1` through `H8` variants
- Targeted dangerous-command validation across the offense families the referee enforces
- Validation against the live referee API plus live node containers
- Automatic referee DB backup and restore so the validation does not leave lasting score or ban state behind

## Poll Cadence

- Team creation is expected to be immediate
- Scoring is expected to land on the next poll
- Recommended live cadence: `POLL_INTERVAL_SECONDS=10`
- For rule validation, the harness uses `POST /api/poll` to force a single scoring cycle after each mutation

## Safe Capture Commands

These are the final state-changing commands that must not trigger offenses when used correctly.

### Generic Safe Capture

Run this as root inside the solved container:

```sh
printf '%s\n' "$TEAM_NAME" > /root/king.txt
chmod 644 /root/king.txt
chmod 700 /root
```

Expected result:
- no `violation` events
- no `ban` events
- one `points_awarded` event once quorum exists

### H1B Allowed Credential Path

`H1B` intentionally uses `/root/.ssh/authorized_keys`.

Allowed mutation:

```sh
mkdir -p /root/.ssh
printf '%s\n' 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCvalidation validation' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
printf '%s\n' "$TEAM_NAME" > /root/king.txt
chmod 644 /root/king.txt
chmod 700 /root
```

Expected result:
- no `authkeys_changed` offense on `H1B`
- one clean point once quorum exists

### H7B Allowed Shadow Path

`H7B` intentionally uses `/etc/shadow`.

Allowed validation mutation:

```sh
cp -p /etc/shadow /tmp/val_shadow.bak
awk -F: 'BEGIN{OFS=":"} $1=="root"{$3=($3=="0"?"1":"0")}1' /tmp/val_shadow.bak > /etc/shadow
printf '%s\n' "$TEAM_NAME" > /root/king.txt
chmod 644 /root/king.txt
chmod 700 /root
```

Expected result:
- no `shadow_changed` offense on `H7B`
- one clean point once quorum exists

Restore immediately after the validation poll:

```sh
cp -p /tmp/val_shadow.bak /etc/shadow
rm -f /tmp/val_shadow.bak
```

### H1C One-Shot Write Pattern

`H1C` previously collided with the watchdog rule. A normal one-shot command that references `king.txt` must stay clean.

Example validation command:

```sh
sh -lc "printf '%s\n' '$TEAM_NAME' > /root/king.txt; chmod 644 /root/king.txt; chmod 700 /root; sleep 12"
```

Expected result:
- no `watchdog_process`
- one clean point once quorum exists

## Dangerous Command Matrix

These are the commands that should trigger offenses. The harness attempts every supported command family and records unsupported cases explicitly.

| Offense | Trigger command | Expected result |
|---|---|---|
| `king_perm_changed` | `chmod 600 /root/king.txt` | warning / ban ladder for offense `1` |
| `king_owner_changed` | `chown 65534:65534 /root/king.txt` | warning / ban ladder for offense `2` |
| `king_immutable` | `chattr +i /root/king.txt` | warning / ban ladder for offense `3` |
| `king_deleted` | `rm -f /root/king.txt` | warning / ban ladder for offense `4` |
| `king_not_regular` | `rm -f /root/king.txt && ln -s /etc/passwd /root/king.txt` | warning / ban ladder for offense `5` |
| `root_dir_perm_changed` | `chmod 755 /root` | warning / ban ladder for offense `6` |
| `cron_king_persistence` | `printf '* * * * * root echo bad >> /root/king.txt\n' > /etc/cron.d/zz-val-king` | warning / ban ladder for offense `7` |
| `watchdog_process` | `ln -sf /bin/sleep /tmp/incrond && /tmp/incrond 120 &` | warning / ban ladder for offense `8` |
| `service_ports_changed` | `php -S 0.0.0.0:54321 -t /tmp &` or equivalent extra listener | warning / ban ladder for offense `12` |
| `iptables_changed` | `iptables -A INPUT -p tcp --dport 54321 -j ACCEPT` | warning / ban ladder for offense `13` |
| `shadow_changed` | alter `/etc/shadow` on a non-exempt variant | warning / ban ladder for offense `14` |
| `authkeys_changed` | alter `/root/.ssh/authorized_keys` on a non-exempt variant | warning / ban ladder for offense `15` |

## Machine Matrix

These are the solve paths that the validation harness treats as legitimate challenge completion context.

| Machine | Port(s) | Initial vector | PrivEsc vector | Safe final action |
|---|---:|---|---|---|
| `H1A` | `10001` | WordPress Reflex Gallery RCE | SUID `/usr/bin/find` | generic safe capture |
| `H1B` | `10002` | Unauthenticated Redis | write SSH key to `/root/.ssh/` | `H1B` allowed credential path |
| `H1C` | `10004` | PHP ping command injection | SUID `/usr/local/bin/net-search` | `H1C` one-shot write pattern |
| `H2A` | `10010` | Jenkins Script Console | `sudo python3` | generic safe capture |
| `H2B` | `10011` | PHP SQLi | MySQL FILE/UDF | generic safe capture |
| `H2C` | `10012` | Tomcat default creds | PwnKit | generic safe capture |
| `H3A` | `10020` | SMB share leaks SSH key | `lxd` breakout | generic safe capture |
| `H3B` | `10022` | Drupalgeddon2 | root cron `tar *` | generic safe capture |
| `H3C` | `10023` | exposed `.git` | `perl` with `cap_setuid` | generic safe capture |
| `H4A` | `10030` | Node deserialization | root password in backups | generic safe capture |
| `H4B` | `10031` | Spring4Shell | root password in `.bash_history` | generic safe capture |
| `H4C` | `10032` | SSRF to internal API | internal root API exec | generic safe capture |
| `H5A` | `10040` | Webmin RCE | direct root | generic safe capture |
| `H5B` | `10041` | ElasticSearch scripting | writable `/etc/passwd` | generic safe capture |
| `H5C` | `10042` | Apache Struts | `LD_PRELOAD` sudo | generic safe capture |
| `H6A` | `10050` | distcc | NFS `no_root_squash` | generic safe capture |
| `H6B` | `10052`,`10054` | MongoDB no auth | `docker` group | generic safe capture |
| `H6C` | `10053`,`10055` | Heartbleed | `sudo systemctl start` | generic safe capture |
| `H7A` | `10060`,`10061` | SNMP public | hijack root `tmux` | generic safe capture |
| `H7B` | `10062` | Grafana traversal/admin exec | world-writable `/etc/shadow` | `H7B` allowed shadow path |
| `H7C` | `10063` | RSync anonymous write | PATH-hijack cron | generic safe capture |
| `H8A` | `10070` | PHPMyAdmin root:blank | MySQL UDF shell | generic safe capture |
| `H8B` | `10071` | Flask/Jinja2 SSTI | writable sudoers trick | generic safe capture |
| `H8C` | `10072` | Laravel debug RCE | SUID `bash_suid -p` | generic safe capture |

## Validation Sequence

1. Back up the live referee DB.
2. Record the current runtime state and current series.
3. Reduce live `POLL_INTERVAL_SECONDS` to `10` if the environment still uses `30`.
4. Rotate series `1` through `8`, validate health, and for each variant:
   - run the safe capture mutation on two nodes
   - force one poll
   - confirm one clean point and zero offense events
5. Run the challenge-specific safe-edge tests:
   - `H1B authkeys`
   - `H1C one-shot king write`
   - `H7B shadow`
6. Run the dangerous command matrix:
   - exhaustive `root_dir_perm_changed` on all 24 variants
   - targeted probes for offenses `1,2,3,4,5,7,8,12,13,14,15`
7. Rotate back to the original series.
8. Restore the original referee DB.
9. Restart `koth-referee`.
10. Confirm runtime state and current series match the original pre-validation state.

## Signoff Criteria

Validation passes only if all of these are true:

- every safe capture path across all 24 variants scores cleanly
- `H1B`, `H1C`, and `H7B` do not false-ban on their intended paths
- every dangerous command that the environment supports produces the expected offense
- unsupported dangerous probes are explicitly reported as unsupported, not silently skipped
- the original referee DB state is restored at the end
