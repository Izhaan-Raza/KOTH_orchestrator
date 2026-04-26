FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    apache2 \
    mysql-server \
    php \
    php-mysql \
    sudo \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && \
    chmod 644 /root/king.txt && \
    chmod 700 /root

COPY app/ /var/www/html/
RUN rm -f /var/www/html/index.html && \
    chown -R www-data:www-data /var/www/html/ && \
    chmod -R 755 /var/www/html/

COPY mysql-setup.sql /docker-entrypoint-initdb.d/setup.sql

# PrivEsc Vector: www-data can run the mysql client as root
RUN echo "www-data ALL=(root) NOPASSWD: /usr/bin/mysql" >> /etc/sudoers

EXPOSE 80

CMD ["/bin/bash", "-c", \
    "service mysql start && \
    while ! mysqladmin ping --silent; do sleep 1; done && \
    if ! mysql -Nse \"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='kothdb'\" | grep -q '^kothdb$'; then mysql < /docker-entrypoint-initdb.d/setup.sql; fi && \
    service apache2 start && \
    tail -f /var/log/apache2/error.log"]
