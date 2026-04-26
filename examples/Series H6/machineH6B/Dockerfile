FROM mongo:4.4

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    docker.io \
    openssh-server \
    passwd \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create low-priv user and add to docker group (PrivEsc via docker.sock)
RUN useradd -m -s /bin/bash mongouser && echo 'mongouser:letmein' | chpasswd
RUN groupadd docker 2>/dev/null || true
RUN usermod -aG docker mongouser
RUN mkdir -p /var/run/sshd && \
    echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && \
    echo 'PermitRootLogin no' >> /etc/ssh/sshd_config

# Seed MongoDB with password hashes to crack
COPY seed.js /seed.js

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 27017 22

CMD ["/start.sh"]
