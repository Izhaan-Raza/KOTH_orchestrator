FROM tomcat:9.0.31-jdk8-openjdk

ENV DEBIAN_FRONTEND=noninteractive

RUN printf '%s\n' \
    'deb http://archive.debian.org/debian buster main' \
    'deb http://archive.debian.org/debian buster-updates main' \
    'deb http://archive.debian.org/debian-security buster/updates main' \
    > /etc/apt/sources.list && \
    printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99archive

RUN apt-get update && apt-get install -y \
    gcc \
    make \
    sudo \
    wget \
    curl \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Lock down the king file with the standard runtime pattern.
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && \
    chmod 644 /root/king.txt && \
    chmod 700 /root
RUN cp -r /usr/local/tomcat/webapps.dist/* /usr/local/tomcat/webapps/
# Configure Tomcat Credentials
COPY tomcat-users.xml /usr/local/tomcat/conf/tomcat-users.xml
COPY context.xml /usr/local/tomcat/webapps/manager/META-INF/context.xml
COPY context.xml /usr/local/tomcat/webapps/host-manager/META-INF/context.xml

# Create low-priv user and change ownership of Tomcat directories
RUN useradd -m -s /bin/bash tomcatuser && \
    chown -R tomcatuser:tomcatuser /usr/local/tomcat

# Deterministic PwnKit simulation: vulnerable pkexec replacement reachable from the low-priv shell.
COPY pkexec.c /tmp/pkexec.c
RUN gcc /tmp/pkexec.c -o /usr/bin/pkexec && \
    chown root:root /usr/bin/pkexec && \
    chmod 4755 /usr/bin/pkexec && \
    rm -f /tmp/pkexec.c

# IMPORTANT: Run as low-priv user
USER tomcatuser

EXPOSE 8080

CMD ["catalina.sh", "run"]
