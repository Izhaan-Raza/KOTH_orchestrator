#!/bin/bash

# Start SLA HTTP server on port 9999
python3 -m http.server 9999 --directory /root &

sleep 2

# Run Laravel development server as laraveluser
su -s /bin/bash laraveluser -c "cd /opt/laravel && php artisan serve --host=0.0.0.0 --port=8000"

# Keep alive
tail -f /dev/null
