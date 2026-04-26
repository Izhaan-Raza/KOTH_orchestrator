FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    adduser \
    libfontconfig1 \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Install Grafana 8.3.0 (vulnerable to CVE-2021-43798 path traversal)
RUN wget -q https://dl.grafana.com/oss/release/grafana_8.3.0_amd64.deb -O /tmp/grafana.deb && \
    dpkg -i /tmp/grafana.deb && rm /tmp/grafana.deb || \
    (echo "Grafana download failed, using stub" && mkdir -p /usr/share/grafana)

# Create grafana user to run the service
RUN useradd -m -s /bin/bash grafana 2>/dev/null || true
RUN mkdir -p /etc/grafana && \
    printf '[security]\nadmin_user = admin\nadmin_password = traversalWins\n' > /etc/grafana/grafana.ini

# PrivEsc: /etc/shadow is writable by all (insecure permissions)
RUN chmod 666 /etc/shadow

# Grafana stub if real install fails
COPY grafana-stub.py /opt/grafana-stub.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 3000

CMD ["/start.sh"]
