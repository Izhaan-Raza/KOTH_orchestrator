FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    apache2 \
    mysql-server \
    php \
    php-mysql \
    php-curl \
    php-gd \
    php-mbstring \
    php-xml \
    php-xmlrpc \
    php-soap \
    php-intl \
    php-zip \
    wget \
    curl \
    findutils \
    && rm -rf /var/lib/apt/lists/*

# King file (Locked down: readable by SLA bot, writable ONLY by root)
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Apache config
COPY apache2.conf /etc/apache2/sites-available/000-default.conf
RUN a2enmod rewrite

# Setup script (Executes during the build)
COPY setup.sh /setup.sh
RUN chmod +x /setup.sh && /setup.sh

EXPOSE 80

# Keep services running robustly without relying on logs or crashing on warnings
CMD ["/bin/bash", "-c", "mkdir -p /var/run/mysqld && chown mysql:mysql /var/run/mysqld && service mysql start ; service apache2 start ; tail -f /dev/null"]