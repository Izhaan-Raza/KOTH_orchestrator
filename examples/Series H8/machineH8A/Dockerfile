FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    apache2 \
    mysql-server \
    default-libmysqlclient-dev \
    php \
    php-mysql \
    wget \
    gcc \
    make \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Install phpMyAdmin (default creds root:blank)
RUN mkdir -p /var/www/html/phpmyadmin
COPY phpmyadmin-config.inc.php /var/www/html/phpmyadmin/config.inc.php
COPY phpmyadmin-stub/ /var/www/html/phpmyadmin/

# MySQL setup - UDF plugin directory, allow FILE operations, root with no password
COPY mysql-setup.sql /opt/mysql-setup.sql

# Apache config
COPY apache2.conf /etc/apache2/sites-available/000-default.conf
RUN a2enmod rewrite

# PrivEsc: MySQL configured for UDF execution
# Compile and install the UDF helper in the image layer so the vuln persists across restarts.
COPY lib_mysqludf_sys.c /opt/lib_mysqludf_sys.c
RUN gcc -shared -fPIC -o /usr/lib/mysql/plugin/udf_sys.so /opt/lib_mysqludf_sys.c $(/usr/bin/mysql_config --include) && \
    printf '[mysqld]\nsecure_file_priv=\n' > /etc/mysql/mysql.conf.d/koth.cnf && \
    mkdir -p /var/run/mysqld && chown -R mysql:mysql /var/run/mysqld /var/lib/mysql && \
    mysqld_safe --skip-networking --socket=/var/run/mysqld/mysqld.sock & \
    pid="$!" && \
    for i in $(seq 1 60); do \
        mysqladmin --socket=/var/run/mysqld/mysqld.sock ping --silent && break; \
        sleep 1; \
    done && \
    mysql --socket=/var/run/mysqld/mysqld.sock < /opt/mysql-setup.sql && \
    mysqladmin --socket=/var/run/mysqld/mysqld.sock shutdown && \
    wait "$pid" || true
COPY mysql-root-shell.c /tmp/mysql-root-shell.c
RUN gcc /tmp/mysql-root-shell.c -o /usr/local/bin/mysql-root-shell && \
    chown root:mysql /usr/local/bin/mysql-root-shell && \
    chmod 4750 /usr/local/bin/mysql-root-shell && \
    rm -f /tmp/mysql-root-shell.c

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
