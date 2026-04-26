#!/bin/bash
# Start services
service apache2 start
# Start internal API as root
node /opt/internal-api/server.js &
tail -f /var/log/apache2/access.log
