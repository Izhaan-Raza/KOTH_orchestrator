#!/bin/bash

# KoTH Hour 3 Orchestrator
COMPOSE_FILE="docker-compose.yml"

case "$1" in
    cache|build)
        echo "[*] PRE-EVENT CACHING: Building Hour 3 series..."
        # We use --no-cache here to ensure your Dockerfile and code changes are applied
        docker-compose -f $COMPOSE_FILE build --pull --no-cache
        echo "[+] Hour 3 images are fully baked and cached!"
        ;;
    start)
        echo "[*] DEPLOYING HOUR 3..."
        # --force-recreate ensures fresh containers; -d runs in background
        docker-compose -f $COMPOSE_FILE up -d --force-recreate || exit 1
        echo "[+] Hour 3 is live! Machines H3A (Samba+SSH), H3B (Drupal), and H3C (WebApp+Git) are running."
        ;;
    stop)
        echo "[*] TEARING DOWN HOUR 3..."
        # -v is CRITICAL: it nukes the database and container states so the next round starts clean
        docker-compose -f $COMPOSE_FILE down -v || exit 1
        echo "[+] Hour 3 has been completely destroyed."
        ;;
    status)
        docker-compose -f $COMPOSE_FILE ps
        ;;
    *)
        echo "Usage: ./orchestrator_h3.sh {build|start|stop|status}"
        echo "  build  - Run this after changing Dockerfiles or code."
        echo "  start  - Instantly boot the round."
        echo "  stop   - Nuke the round and wipe player progress."
        exit 1
        ;;
esac
