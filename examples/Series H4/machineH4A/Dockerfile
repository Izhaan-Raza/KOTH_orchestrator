FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Added python3 for shell upgrading (so 'su root' works)
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    python3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Lock down the king file (Root Only)
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && \
    chmod 644 /root/king.txt && \
    chmod 700 /root

# Actually SET the root password so the 'su' command works
RUN echo 'root:r00tme' | chpasswd

# PrivEsc: Leave the breadcrumbs for the players
RUN mkdir -p /var/backups && \
    echo 'root:$6$koth$V5R8Y2bKJ9L1mN3P4qQ0wXsUoIaEzFhGcDtRvWnMeKpBjHuZxCyA7l6d5f4g3h2i1.:19000:0:99999:7:::' \
    > /var/backups/shadow.bak && \
    echo "Root password backup: r00tme" > /var/backups/README.txt && \
    chmod 644 /var/backups/shadow.bak && \
    chmod 644 /var/backups/README.txt

# Deploy Node.js app
RUN mkdir -p /app
COPY app/ /app/
WORKDIR /app
RUN npm install

# Create low-priv user and own the app directory
RUN useradd -m -s /bin/bash nodeuser && echo 'nodeuser:nodepass' | chpasswd
RUN chown -R nodeuser:nodeuser /app

# IMPORTANT: Drop privileges before starting the server
USER nodeuser

EXPOSE 3000

CMD ["node", "/app/server.js"]
