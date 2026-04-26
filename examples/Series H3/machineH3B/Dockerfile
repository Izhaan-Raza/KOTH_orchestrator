FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Use MariaDB instead of MySQL 8 (Drupal 7.57 is incompatible with MySQL 8)
RUN apt-get update && apt-get install -y \
    apache2 \
    php7.4 \
    php7.4-mysql \
    php7.4-gd \
    php7.4-xml \
    php7.4-cli \
    php7.4-json \
    libapache2-mod-php7.4 \
    mariadb-server \
    cron \
    tar \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Install Drupal 7.57 (vulnerable to Drupalgeddon2 CVE-2018-7600)
RUN wget -q https://ftp.drupal.org/files/projects/drupal-7.57.tar.gz -P /tmp/ && \
    tar -xzf /tmp/drupal-7.57.tar.gz -C /var/www/html/ --strip-components=1 && \
    rm /tmp/drupal-7.57.tar.gz

# Install drush 8 (compatible with Drupal 7)
RUN wget -q https://github.com/drush-ops/drush/releases/download/8.4.12/drush.phar -O /usr/local/bin/drush && \
    chmod +x /usr/local/bin/drush

# Apache config
COPY apache2.conf /etc/apache2/sites-available/000-default.conf
RUN a2enmod rewrite php7.4

# Prepare sites/default permissions for installer
RUN mkdir -p /var/www/html/sites/default/files && \
    chmod 777 /var/www/html/sites/default/files && \
    chmod 777 /var/www/html/sites/default && \
    cp /var/www/html/sites/default/default.settings.php /var/www/html/sites/default/settings.php && \
    chmod 666 /var/www/html/sites/default/settings.php && \
    chown -R www-data:www-data /var/www/html/

# Set up MariaDB and install Drupal via drush
RUN service mysql start && sleep 5 && \
    mysql -e "CREATE DATABASE drupal;" && \
    mysql -e "CREATE USER 'drupal'@'localhost' IDENTIFIED BY 'drupal123';" && \
    mysql -e "GRANT ALL ON drupal.* TO 'drupal'@'localhost';" && \
    mysql -e "FLUSH PRIVILEGES;" && \
    cd /var/www/html && \
    drush site-install standard \
        --db-url=mysql://drupal:drupal123@localhost/drupal \
        --site-name="KoTH H3B" \
        --account-name=admin \
        --account-pass=admin123 \
        --account-mail=admin@koth.local \
        --yes 2>&1 || true && \
    mysql drupal -e "SHOW TABLES LIKE 'users';" | grep -q users

# Overwrite with CTF settings.php
COPY settings.php /var/www/html/sites/default/settings.php

# Fix permissions
RUN chown -R www-data:www-data /var/www/html/ && \
    chmod -R 755 /var/www/html/ && \
    chmod 777 /var/www/html/sites/default/files

# PrivEsc: Writable directory where root runs `tar *` via cron
RUN mkdir -p /opt/backups && chmod 777 /opt/backups
RUN echo "* * * * * root cd /opt/backups && tar czf /tmp/backup.tar.gz *" >> /etc/crontab

EXPOSE 80

CMD ["/bin/bash", "-c", \
    "service mysql start && sleep 3 && \
     service cron start && \
     service apache2 start && \
     tail -f /var/log/apache2/error.log"]
