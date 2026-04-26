#!/bin/bash

# KoTH Hour 8 Orchestrator
COMPOSE_FILE="docker-compose.yml"

case "$1" in
    cache|build)
        echo "[*] PRE-EVENT CACHING: Building Hour 8 series..."
        # We use --no-cache here to ensure your setup.sh changes are actually applied
        docker-compose -f $COMPOSE_FILE build --pull --no-cache
        echo "[+] Hour 8 images are fully baked and cached!"
        ;;
    start)
        echo "[*] DEPLOYING HOUR 8..."
        # --force-recreate ensures fresh containers; -d runs in background
        docker-compose -f $COMPOSE_FILE up -d --force-recreate || exit 1
        echo "[+] Hour 8 is live! Machines H8A, H8B, and H8C are running."
        ;;
    stop)
        echo "[*] TEARING DOWN HOUR 8..."
        # -v is CRITICAL: it nukes the database volumes so the next round starts clean
        docker-compose -f $COMPOSE_FILE down -v || exit 1
        echo "[+] Hour 8 has been completely destroyed (Volumes wiped)."
        ;;
    status)
        docker-compose -f $COMPOSE_FILE ps
        ;;
    *)
        echo "Usage: ./orchestrator_h8.sh {build|start|stop|status}"
        echo "  build  - Run this after changing setup.sh or Dockerfiles."
        echo "  start  - Instantly boot the round."
        echo "  stop   - Nuke the round and wipe player databases."
        exit 1
        ;;
esac
