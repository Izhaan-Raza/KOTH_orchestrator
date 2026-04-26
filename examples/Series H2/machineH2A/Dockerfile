FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Jenkins requires Java 11 (works for 2.235.1)
RUN apt-get update && apt-get install -y \
    openjdk-11-jdk \
    wget \
    curl \
    sudo \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Jenkins LTS
RUN wget -q -O /tmp/jenkins.war https://updates.jenkins.io/download/war/2.235.1/jenkins.war

# King file - LOCKED DOWN (Requires root/sudo to write)
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && \
    chmod 644 /root/king.txt && \
    chmod 700 /root

# Create jenkins user
RUN useradd -m -s /bin/bash jenkins && echo 'jenkins:jenkins' | chpasswd

# The Intended PrivEsc Vector: sudo python3
RUN echo "jenkins ALL=(ALL) NOPASSWD: /usr/bin/python3" >> /etc/sudoers

# Jenkins Setup
ENV JENKINS_HOME=/var/jenkins_home
RUN mkdir -p /var/jenkins_home/init.groovy.d && \
    chown -R jenkins:jenkins /var/jenkins_home

# Disable Jenkins security via init script
COPY disable-security.groovy /var/jenkins_home/init.groovy.d/disable-security.groovy
RUN chown jenkins:jenkins /var/jenkins_home/init.groovy.d/disable-security.groovy

EXPOSE 8080

# Run as jenkins user
USER jenkins
ENTRYPOINT ["java", \
    "-Djenkins.install.runSetupWizard=false", \
    "-Dhudson.security.csrf.GlobalCrumbIssuerConfiguration.DISABLE_CSRF_PROTECTION=true", \
    "-jar", "/tmp/jenkins.war", "--httpPort=8080"]
