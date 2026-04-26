FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    snmpd \
    tmux \
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Configure SNMPd - public community string, leaks process list
COPY snmpd.conf /etc/snmp/snmpd.conf

# Create a low-priv SSH foothold whose password is leaked through the process list.
RUN useradd -m -s /bin/bash opsuser && echo 'opsuser:snmpops' | chpasswd

# Create a root tmux session that stays alive (hijackable)
# Attacker can attach to the root tmux session if they get a shell on the box
RUN mkdir -p /root && touch /root/.tmux_active

COPY start.sh /start.sh
RUN chmod +x /start.sh

# SSH setup
RUN mkdir /var/run/sshd && \
    echo 'PermitRootLogin no' >> /etc/ssh/sshd_config && \
    echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config

EXPOSE 161/udp 22

CMD ["/start.sh"]
