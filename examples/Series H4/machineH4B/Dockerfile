FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Spring4Shell needs Java 8 or Java 11 with Spring Framework < 5.3.18
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create a low-priv user
RUN useradd -m -s /bin/bash springuser && echo 'springuser:spring123' | chpasswd

# PrivEsc: Root password visible in bash_history
RUN mkdir -p /root && \
    echo 'ls -la /root' > /root/.bash_history && \
    echo 'cat /etc/shadow' >> /root/.bash_history && \
    echo 'su -' >> /root/.bash_history && \
    echo 'echo "toor:koth_r00t_2024" | chpasswd' >> /root/.bash_history && \
    echo 'cat /root/king.txt' >> /root/.bash_history && \
    chmod 644 /root/.bash_history

# Set actual root password that matches what's in history
RUN echo 'root:koth_r00t_2024' | chpasswd

# Deploy vulnerable Spring4Shell WAR
# Using a pre-built vulnerable Spring demo app
COPY spring-app/ /opt/spring-app/
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Spring boot app that is vulnerable to Spring4Shell
# The vulnerability exists in Spring Framework <= 5.3.17 with JDK 9+
# Attack vector: send a crafted POST request to any Spring MVC endpoint
WORKDIR /opt/spring-app

EXPOSE 8080

CMD ["/run.sh"]
