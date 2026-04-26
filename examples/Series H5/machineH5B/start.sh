#!/bin/sh
echo "[H5B] Starting deterministic Elasticsearch 6.x simulation with dynamic scripting enabled"
exec su -s /bin/sh www-data -c 'python3 /opt/es-stub.py'
