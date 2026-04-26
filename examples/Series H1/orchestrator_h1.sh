#!/bin/bash

# KoTH Hour 1 Orchestrator
COMPOSE_FILE="docker-compose.yml"

case "$1" in
    cache|build)
        echo "[*] PRE-EVENT CACHING: Building Hour 1 series..."
        # We use --no-cache here to ensure your setup.sh changes are actually applied
        docker-compose -f $COMPOSE_FILE build --pull --no-cache
        echo "[+] Hour 1 images are fully baked and cached!"
        ;;
    start)
        echo "[*] DEPLOYING HOUR 1..."
        # --force-recreate ensures fresh containers; -d runs in background
        docker-compose -f $COMPOSE_FILE up -d --force-recreate || exit 1
        echo "[+] Hour 1 is live! Machines H1A, H1B, and H1C are running."
        ;;
    stop)
        echo "[*] TEARING DOWN HOUR 1..."
        # -v is CRITICAL: it nukes the database volumes so the next round starts clean
        docker-compose -f $COMPOSE_FILE down -v || exit 1
        echo "[+] Hour 1 has been completely destroyed (Volumes wiped)."
        ;;
    status)
        docker-compose -f $COMPOSE_FILE ps
        ;;
    *)
        echo "Usage: ./orchestrator_h1.sh {build|start|stop|status}"
        echo "  build  - Run this after changing setup.sh or Dockerfiles."
        echo "  start  - Instantly boot the round."
        echo "  stop   - Nuke the round and wipe player databases."
        exit 1
        ;;
esac