FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    distcc \
    gcc \
    nfs-kernel-server \
    nfs-common \
    rpcbind \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create a low-priv user that distcc runs as
RUN useradd -m -s /bin/bash distccuser && echo 'distccuser:distcc' | chpasswd

# Configure distcc - listen on all interfaces, no auth (CVE-2004-2687)
COPY distcc.conf /etc/distcc/hosts
RUN echo "STARTDISTCC=true" > /etc/default/distcc && \
    echo "ALLOWEDNETS=0.0.0.0/0" >> /etc/default/distcc && \
    echo "LISTENER=0.0.0.0" >> /etc/default/distcc && \
    echo "JOBS=" >> /etc/default/distcc && \
    echo "NICE=10" >> /etc/default/distcc

# NFS setup with no_root_squash (PrivEsc vector)
# Attackers can mount this NFS share and write SUID binaries as root (due to no_root_squash)
RUN mkdir -p /srv/nfs/share && chmod 777 /srv/nfs/share
RUN echo "/srv/nfs/share *(rw,sync,no_subtree_check,no_root_squash)" > /etc/exports

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 3632 2049 111

CMD ["/start.sh"]
