FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openjdk-8-jdk \
    wget \
    curl \
    sudo \
    gcc \
    make \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create a low-priv user (struts app runs as this user)
RUN useradd -m -s /bin/bash strutsuser && echo 'strutsuser:struts123' | chpasswd

# PrivEsc: preserve LD_PRELOAD for a single allowed binary so the challenge is the preload escape,
# not unrestricted passwordless sudo.
RUN printf '%s\n' \
    'Defaults:strutsuser env_keep += "LD_PRELOAD"' \
    'strutsuser ALL=(root) NOPASSWD: /usr/bin/find' \
    > /etc/sudoers.d/strutsuser-ld-preload && \
    chmod 440 /etc/sudoers.d/strutsuser-ld-preload

# Apache Struts CVE-2017-5638 simulation (Content-Type header injection -> RCE)
# Using a Python-based stub that simulates the Struts 2 endpoint
COPY struts-stub.py /opt/struts-stub.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8080

CMD ["/start.sh"]
