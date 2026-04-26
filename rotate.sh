#!/bin/bash
# =============================================================================
# LOCAL DEVELOPMENT ONLY — NOT the production control plane.
# In production, series rotation is driven by referee-server/ over SSH.
# See docs/operations/full-deployment-runbook.md for the real deployment model.
# =============================================================================
# KoTH Master Orchestrator (v1 syntax fix)
# Usage: ./rotate.sh [ROUND_NUMBER]

ROUND=$1

if [[ ! "$ROUND" =~ ^[1-8]$ ]]; then
    echo "Error: Round must be a number between 1 and 8."
    echo "Usage: ./rotate.sh <round_number>"
    exit 1
fi

echo "[*] Initiating KoTH Mutation Sequence - Starting Round $ROUND..."

# Step 1: Nuke the board (Using docker-compose with a hyphen)
echo "[!] Tearing down current targets and wiping volumes..."
docker-compose down -v --remove-orphans

# Step 2: System cleanup
echo "[*] Pruning dangling networks..."
docker network prune -f

# Step 3: Deploy the new round
A="machineH${ROUND}A"
B="machineH${ROUND}B"
C="machineH${ROUND}C"

echo "[+] Spinning up targets for Round $ROUND: $A, $B, $C..."
docker-compose up -d --build $A $B $C

# Step 4: Verify deployment
echo "[+] Mutation complete. Active containers:"
docker-compose ps