FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    apache2 \
    php \
    git \
    perl \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 666 /root/king.txt && chmod 777 /root

# Create a web app with exposed .git directory
RUN mkdir -p /var/www/html/webapp

# Init a git repo with credentials in history
RUN cd /var/www/html/webapp && \
    git init && \
    git config user.email "admin@koth.local" && \
    git config user.name "Admin" && \
    echo "DB_PASS=s3cr3tAdm1nPa55!" > .env && \
    echo "ADMIN_USER=admin" >> .env && \
    echo "ADMIN_PASS=koth_admin_2024" >> .env && \
    git add .env && \
    git commit -m "Add environment config" && \
    rm .env && \
    git commit -am "Remove env file for security" 2>/dev/null || \
    (git add -A && git commit -m "Remove env file for security")

# Simple PHP app that requires credentials found in git history
COPY app/ /var/www/html/webapp/
RUN chown -R www-data:www-data /var/www/html/ && \
    chmod -R 755 /var/www/html/

# Apache config - serves .git directory (no deny rule)
COPY apache2.conf /etc/apache2/sites-available/000-default.conf
RUN a2enmod rewrite

# PrivEsc: perl has cap_setuid capability
RUN setcap cap_setuid+eip /usr/bin/perl

EXPOSE 80

CMD ["/bin/bash", "-c", "service apache2 start && tail -f /var/log/apache2/error.log"]
