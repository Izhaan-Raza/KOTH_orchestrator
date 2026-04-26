#!/bin/bash

# KoTH Hour 4 Orchestrator
COMPOSE_FILE="docker-compose.yml"

case "$1" in
    cache|build)
        echo "[*] PRE-EVENT CACHING: Building Hour 4 series..."
        # We use --no-cache here to ensure your Dockerfile and code changes are applied
        docker-compose -f $COMPOSE_FILE build --pull --no-cache
        echo "[+] Hour 4 images are fully baked and cached!"
        ;;
    start)
        echo "[*] DEPLOYING HOUR 4..."
        # --force-recreate ensures fresh containers; -d runs in background
        docker-compose -f $COMPOSE_FILE up -d --force-recreate || exit 1
        echo "[+] Hour 4 is live! Machines H4A (Node.js/shadow), H4B (Spring4Shell), and H4C (PHP SSRF to Node.js) are running."
        ;;
    stop)
        echo "[*] TEARING DOWN HOUR 4..."
        # -v is CRITICAL: it nukes the database and container states so the next round starts clean
        docker-compose -f $COMPOSE_FILE down -v || exit 1
        echo "[+] Hour 4 has been completely destroyed."
        ;;
    status)
        docker-compose -f $COMPOSE_FILE ps
        ;;
    *)
        echo "Usage: ./orchestrator_h4.sh {build|start|stop|status}"
        echo "  build  - Run this after changing Dockerfiles or code."
        echo "  start  - Instantly boot the round."
        echo "  stop   - Nuke the round and wipe player progress."
        exit 1
        ;;
esac
