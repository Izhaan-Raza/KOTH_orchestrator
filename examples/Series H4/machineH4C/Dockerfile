FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    apache2 \
    php \
    php-curl \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Deploy SSRF vulnerable PHP app
COPY webapp/ /var/www/html/
RUN chown -R www-data:www-data /var/www/html/

# Apache config
COPY apache2.conf /etc/apache2/sites-available/000-default.conf
RUN a2enmod rewrite

# PrivEsc: Internal Node.js API running as root that executes commands
# Listens on 127.0.0.1:1337 - only reachable via SSRF
COPY internal-api/ /opt/internal-api/
WORKDIR /opt/internal-api
RUN npm install

# Create startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
