FROM tomcat:9.0.31-jdk8-openjdk

ENV DEBIAN_FRONTEND=noninteractive

# Install additional tools for PwnKit PrivEsc
RUN apt-get update && apt-get install -y \
    gcc \
    make \
    pkexec \
    policykit-1 \
    sudo \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 666 /root/king.txt && chmod 777 /root

# Configure Tomcat with default credentials (tomcat:tomcat)
COPY tomcat-users.xml /usr/local/tomcat/conf/tomcat-users.xml
COPY context.xml /usr/local/tomcat/webapps/manager/META-INF/context.xml
COPY context.xml /usr/local/tomcat/webapps/host-manager/META-INF/context.xml

# Deploy a sample WAR (placeholder - teams upload shell via manager)
RUN echo '<html><body><h1>KoTH App</h1><p>Tomcat is running. Manager at /manager/html</p></body></html>' \
    > /usr/local/tomcat/webapps/ROOT/index.html

# PrivEsc: PwnKit (CVE-2021-4034) - pkexec is installed with SUID
# pkexec comes with SUID bit set by default in policykit-1
# Verify it's there (Polkit version older than 0.121 is vulnerable)
RUN ls -la /usr/bin/pkexec

# Create a low-priv user for Tomcat to run as
RUN useradd -m -s /bin/bash tomcatuser && echo 'tomcatuser:tomcat' | chpasswd

EXPOSE 8080

CMD ["catalina.sh", "run"]
