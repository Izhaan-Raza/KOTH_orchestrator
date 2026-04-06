FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    vsftpd \
    apache2 \
    php \
    cron \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 666 /root/king.txt && chmod 777 /root

# FTP setup - anonymous allowed, writable to web root
RUN mkdir -p /var/ftp/pub && \
    mkdir -p /var/run/vsftpd/empty && \
    chown root:root /var/ftp && \
    chmod 755 /var/ftp && \
    chown ftp:ftp /var/ftp/pub && \
    chmod 777 /var/ftp/pub && \
    mkdir -p /var/ftp/pub/webroot && \
    chmod 777 /var/ftp/pub/webroot && \
    rm -rf /var/www/html && \
    ln -s /var/ftp/pub/webroot /var/www/html

# vsftpd config - anonymous with write
COPY vsftpd.conf /etc/vsftpd.conf

# Apache setup
RUN chmod 777 /var/www/html
RUN chown -R www-data:www-data /var/ftp/pub/webroot

# PrivEsc: World-writable script run by root cron
RUN mkdir -p /opt/scripts && \
    echo '#!/bin/bash\n# Maintenance script' > /opt/scripts/maintenance.sh && \
    chmod 777 /opt/scripts/maintenance.sh

# Cron job as root running the world-writable script every minute
RUN echo "* * * * * root /opt/scripts/maintenance.sh" >> /etc/crontab

EXPOSE 21 80

CMD ["/bin/bash", "-c", \
    "service rsyslog start; service cron start; service apache2 start; vsftpd /etc/vsftpd.conf"]
