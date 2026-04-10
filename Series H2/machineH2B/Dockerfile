FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    apache2 \
    mysql-server \
    php \
    php-mysql \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 666 /root/king.txt && chmod 777 /root

# Deploy vulnerable PHP app
COPY app/ /var/www/html/
RUN chown -R www-data:www-data /var/www/html/ && chmod -R 755 /var/www/html/

# Apache config
COPY apache2.conf /etc/apache2/sites-available/000-default.conf
RUN a2enmod rewrite

# MySQL setup - configure to run queries as root (FILE privilege + sys_exec via UDF)
# MySQL itself runs as mysql user but we configure it to allow dangerous operations
COPY mysql-setup.sql /docker-entrypoint-initdb.d/setup.sql

EXPOSE 80

CMD ["/bin/bash", "-c", \
    "service mysql start && sleep 3 && \
     mysql < /docker-entrypoint-initdb.d/setup.sql && \
     service apache2 start && \
     tail -f /var/log/apache2/error.log"]
