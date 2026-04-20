# Participant Hard-Bound Rules

These rules are mandatory for every participant and every team during the event.

## Core Boundary

1. A team may attack only the currently active challenge target and only through the intended exposed service/entry point for that challenge.
2. A team must not exploit any vulnerability other than the challenge's intended vulnerability and intended privilege-escalation path.
3. A team must not attack non-active series, non-target variants, referee services, the dashboard, the load balancer, the router, the host OS, or any supporting infrastructure.
4. A team must not interfere with another team's connectivity, scoring, visibility, or ability to play.

## Explicitly Forbidden

The following actions are prohibited unless they are the intended solve path for the active challenge:

1. Modifying firewall rules, routing, or network access controls.
2. Opening new listener ports, backdoors, reverse shells, tunnels, or persistence services.
3. Changing `/root` permissions, replacing or deleting `/root/king.txt`, making it immutable, or turning it into a non-regular file.
4. Adding cron jobs, watchdogs, background persistence, or auto-reclaim mechanisms.
5. Modifying `/etc/shadow`, `/root/.ssh/authorized_keys`, or authentication state outside an explicitly intended challenge path.
6. Exploiting additional bugs discovered in the service, container, image, host, load balancer, referee, or surrounding environment.
7. Denial-of-service behavior, brute-force flooding, destructive tampering, sabotage, or any attempt to degrade the platform.
8. Using the challenge foothold to pivot into the nodes, referee host, router, VLAN infrastructure, or unrelated containers.
9. Tampering with logs, scoring state, the database, APIs, admin paths, or dashboard behavior.
10. Any deceptive, abusive, or unsportsmanlike activity intended to bypass the competition design.

## Capture Rule

1. After completing the intended solve path, the team may write only its exact team name into `/root/king.txt`.
2. Teams must not modify ownership, mode, file type, parent directory permissions, or any surrounding protection state for the claim file.
3. Teams must keep their activity limited to what is necessary to obtain root and place a valid claim.

## Enforcement

1. Any exploitation outside the intended challenge path is malpractice.
2. Any prohibited action may lead to immediate ban without warning.
3. Immediate ban may be applied by the referee, operators, or both.
4. A banned team may lose eligibility for points, prizes, ranking, and continued participation.
5. Operator decisions on boundary violations are final during the event.

## Interpretation Rule

If there is any doubt whether an action is in scope, treat it as out of bounds and do not do it until an operator explicitly approves it.
