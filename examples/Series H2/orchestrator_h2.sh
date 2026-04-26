#!/bin/bash

# KoTH Hour 2 Orchestrator
COMPOSE_FILE="docker-compose.yml"

case "$1" in
    cache|build)
        echo "[*] PRE-EVENT CACHING: Building Hour 2 series..."
        # We use --no-cache here to ensure your Dockerfile and code changes are applied
        docker-compose -f $COMPOSE_FILE build --pull --no-cache
        echo "[+] Hour 2 images are fully baked and cached!"
        ;;
    start)
        echo "[*] DEPLOYING HOUR 2..."
        # --force-recreate ensures fresh containers; -d runs in background
        docker-compose -f $COMPOSE_FILE up -d --force-recreate || exit 1
        echo "[+] Hour 2 is live! Machines H2A (Jenkins), H2B (PHP/MySQL), and H2C (Tomcat) are running."
        ;;
    stop)
        echo "[*] TEARING DOWN HOUR 2..."
        # -v is CRITICAL: it nukes the database and container states so the next round starts clean
        docker-compose -f $COMPOSE_FILE down -v || exit 1
        echo "[+] Hour 2 has been completely destroyed."
        ;;
    status)
        docker-compose -f $COMPOSE_FILE ps
        ;;
    *)
        echo "Usage: ./orchestrator_h2.sh {build|start|stop|status}"
        echo "  build  - Run this after changing Dockerfiles or code."
        echo "  start  - Instantly boot the round."
        echo "  stop   - Nuke the round and wipe player progress."
        exit 1
        ;;
esac