#!/bin/bash
# Start Webmin (real install) or fallback to stub
if [ -f /usr/share/webmin/miniserv.pl ]; then
    /etc/init.d/webmin start
    tail -f /var/webmin/miniserv.log
else
    echo "[H5A] Using stub Webmin server (CVE-2019-15107 simulation)"
    python3 /opt/webmin-stub.py
fi
