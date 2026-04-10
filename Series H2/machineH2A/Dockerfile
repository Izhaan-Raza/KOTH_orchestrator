FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Jenkins requires Java
RUN apt-get update && apt-get install -y \
    openjdk-11-jdk \
    wget \
    curl \
    sudo \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Jenkins LTS (old version with no security by default)
RUN wget -q -O /tmp/jenkins.war https://updates.jenkins.io/download/war/2.235.1/jenkins.war

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 666 /root/king.txt && chmod 777 /root

# Create a low-priv user that Jenkins runs as
RUN useradd -m -s /bin/bash jenkins && echo 'jenkins:jenkins' | chpasswd

# PrivEsc: sudo python3 with no password for jenkins user
RUN echo "jenkins ALL=(ALL) NOPASSWD: /usr/bin/python3" >> /etc/sudoers

# Jenkins with no authentication (JAVA_OPTS disable security)
ENV JENKINS_HOME=/var/jenkins_home
RUN mkdir -p /var/jenkins_home && chown jenkins:jenkins /var/jenkins_home

# Disable Jenkins setup wizard and security
RUN mkdir -p /var/jenkins_home/init.groovy.d
COPY disable-security.groovy /var/jenkins_home/init.groovy.d/disable-security.groovy
RUN chown -R jenkins:jenkins /var/jenkins_home

EXPOSE 8080

CMD ["/bin/bash", "-c", \
    "su - jenkins -c 'java -DJENKINS_HOME=/var/jenkins_home \
    -Djenkins.install.runSetupWizard=false \
    -Dhudson.security.csrf.GlobalCrumbIssuerConfiguration.DISABLE_CSRF_PROTECTION=true \
    -jar /tmp/jenkins.war --httpPort=8080'"]
