#!/bin/bash
echo "[H7B] Using deterministic Grafana stub"
exec su -s /bin/bash grafana -c 'python3 /opt/grafana-stub.py'
