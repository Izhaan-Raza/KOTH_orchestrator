FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install vulnerable OpenSSL version (for Heartbleed) - Ubuntu 12.04 era SSL
RUN apt-get update && apt-get install -y \
    openssl \
    libssl-dev \
    apache2 \
    wget \
    sudo \
    openssh-server \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create a low-priv HTTP user
RUN useradd -m -s /bin/bash webuser && echo 'webuser:web123' | chpasswd

# PrivEsc: sudo allows a deterministic systemctl shim to execute unit ExecStart lines as root.
RUN echo "webuser ALL=(ALL) NOPASSWD: /bin/systemctl" >> /etc/sudoers
RUN cat <<'EOF' > /bin/systemctl
#!/bin/bash
set -e

if [ "${1:-}" = "start" ] && [ -n "${2:-}" ] && [ -f "${2}" ]; then
    exec_start=$(awk -F= '/^ExecStart=/{print $2; exit}' "${2}")
    if [ -z "${exec_start}" ]; then
        echo "unit has no ExecStart" >&2
        exit 1
    fi
    exec /bin/bash -lc "${exec_start}"
fi

if [ "${1:-}" = "status" ]; then
    echo "koth-systemctl: ready"
    exit 0
fi

echo "Usage: systemctl start <unit-file> | status" >&2
exit 1
EOF
RUN chmod 755 /bin/systemctl
RUN mkdir -p /var/run/sshd && \
    echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && \
    echo 'PermitRootLogin no' >> /etc/ssh/sshd_config

# Use a Heartbleed-simulating stub since we can't easily downgrade OpenSSL
# The stub serves HTTPS and responds to heartbeat requests with leaked memory
COPY heartbleed-stub.py /opt/heartbleed-stub.py
RUN mkdir -p /etc/ssl/koth && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/koth/server.key \
        -out /etc/ssl/koth/server.crt \
        -subj "/C=US/ST=KoTH/L=CTF/O=KoTH/CN=koth.local" 2>/dev/null

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 443 22

CMD ["/start.sh"]
