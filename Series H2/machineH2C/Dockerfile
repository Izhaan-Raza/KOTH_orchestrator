FROM tomcat:9.0.31-jdk8-openjdk

ENV DEBIAN_FRONTEND=noninteractive

# Install tools for building PwnKit exploit and handling shells
RUN apt-get update && apt-get install -y \
    gcc \
    make \
    policykit-1 \
    sudo \
    wget \
    curl \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Lock down the king file (Strictly Root Only)
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && \
    chmod 600 /root/king.txt && \
    chmod 700 /root

# Configure Tomcat Credentials
COPY tomcat-users.xml /usr/local/tomcat/conf/tomcat-users.xml
COPY context.xml /usr/local/tomcat/webapps/manager/META-INF/context.xml
COPY context.xml /usr/local/tomcat/webapps/host-manager/META-INF/context.xml

# Create low-priv user and change ownership of Tomcat directories
RUN useradd -m -s /bin/bash tomcatuser && \
    chown -R tomcatuser:tomcatuser /usr/local/tomcat

# IMPORTANT: Run as low-priv user
USER tomcatuser

EXPOSE 8080

CMD ["catalina.sh", "run"]