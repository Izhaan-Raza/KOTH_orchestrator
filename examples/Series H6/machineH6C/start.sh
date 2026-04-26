#!/bin/bash
set -e

service ssh start
exec python3 /opt/heartbleed-stub.py
