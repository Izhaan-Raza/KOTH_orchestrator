FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    python3 \
    perl \
    libnet-ssleay-perl \
    libio-socket-ssl-perl \
    libauthen-pam-perl \
    apt-utils \
    && rm -rf /var/lib/apt/lists/*

# King file (placed here; Webmin RCE drops to root directly)
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Install Webmin 1.890 - vulnerable to CVE-2019-15107 (pre-auth RCE as root)
# Webmin before 1.930 with password reset feature is vulnerable
RUN wget -q https://prdownloads.sourceforge.net/webadmin/webmin_1.890_all.deb -O /tmp/webmin.deb || \
    curl -sL https://prdownloads.sourceforge.net/webadmin/webmin_1.890_all.deb -o /tmp/webmin.deb

RUN if [ -f /tmp/webmin.deb ]; then \
        dpkg -i /tmp/webmin.deb || apt-get install -fy; \
    else \
        echo "Webmin download failed - creating stub"; \
        mkdir -p /usr/share/webmin; \
    fi

# Enable password reset feature (creates the vulnerability)
RUN if [ -f /etc/webmin/miniserv.conf ]; then \
        echo "passwd_mode=2" >> /etc/webmin/miniserv.conf; \
        echo "passwd_file=/etc/shadow" >> /etc/webmin/miniserv.conf; \
        echo "passwd_uname_field=user" >> /etc/webmin/miniserv.conf; \
        echo "passwd_pass_field=pass" >> /etc/webmin/miniserv.conf; \
    fi

# Stub server if Webmin fails to download (simulates the vulnerable endpoint)
COPY webmin-stub.py /opt/webmin-stub.py

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 10000

CMD ["/start.sh"]
