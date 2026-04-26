FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    samba \
    openssh-server \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create a low-priv user in lxd group (PrivEsc vector)
RUN useradd -m -s /bin/bash ctfuser && echo 'ctfuser:password' | chpasswd
RUN groupadd lxd 2>/dev/null || true
RUN usermod -aG lxd ctfuser
COPY lxc-shell.c /tmp/lxc-shell.c
RUN gcc /tmp/lxc-shell.c -o /usr/local/bin/lxc && \
    chown root:lxd /usr/local/bin/lxc && \
    chmod 4750 /usr/local/bin/lxc && \
    rm -f /tmp/lxc-shell.c

# Create SMB anonymous share with leaked SSH private key
RUN mkdir -p /srv/smb/share
RUN chmod 777 /srv/smb/share

# Generate SSH key pair and leak private key on SMB share
RUN ssh-keygen -t rsa -b 2048 -f /tmp/ctfuser_key -N '' -q && \
    cp /tmp/ctfuser_key /srv/smb/share/id_rsa && \
    chmod 644 /srv/smb/share/id_rsa && \
    mkdir -p /home/ctfuser/.ssh && \
    cat /tmp/ctfuser_key.pub >> /home/ctfuser/.ssh/authorized_keys && \
    chmod 700 /home/ctfuser/.ssh && \
    chmod 600 /home/ctfuser/.ssh/authorized_keys && \
    chown -R ctfuser:ctfuser /home/ctfuser/.ssh

# Samba config - anonymous share
COPY smb.conf /etc/samba/smb.conf

# SSH config
RUN mkdir /var/run/sshd && \
    echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && \
    echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config

EXPOSE 445 139 22

CMD ["/bin/bash", "-c", \
    "service ssh start && \
     service smbd start && \
     service nmbd start && \
     tail -f /var/log/samba/log.smbd"]
