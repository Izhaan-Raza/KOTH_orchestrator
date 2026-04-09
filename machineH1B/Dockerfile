FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    redis-server \
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

# King file (Read by SLA bot, writable ONLY by root)
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Prepare SSH directory with strict permissions so OpenSSH accepts the keys
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Configure SSH (Crucial: Disable passwords to force the Redis exploit!)
RUN mkdir /var/run/sshd && \
    echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && \
    echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config

EXPOSE 6379 22

# Run Redis directly with vulnerable flags, bypassing the brittle config file
CMD ["/bin/bash", "-c", "service ssh start && redis-server --bind 0.0.0.0 --protected-mode no --daemonize no"]