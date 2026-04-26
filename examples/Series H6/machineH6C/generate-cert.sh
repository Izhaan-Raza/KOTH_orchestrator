#!/bin/bash
mkdir -p /etc/ssl/koth
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/koth/server.key \
    -out /etc/ssl/koth/server.crt \
    -subj "/C=US/ST=KoTH/L=CTF/O=KoTH/CN=koth.local" 2>/dev/null
echo "Certificate generated."
