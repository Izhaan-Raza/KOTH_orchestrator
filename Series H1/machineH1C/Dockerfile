FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    apache2 \
    php \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Setup Web App
RUN rm /var/www/html/index.html
COPY index.php /var/www/html/index.php
RUN chown -R www-data:www-data /var/www/html

# PrivEsc: Create a custom SUID binary named 'net-search' (which is just a copy of 'find')
RUN cp /usr/bin/find /usr/local/bin/net-search && \
    chmod u+s /usr/local/bin/net-search

EXPOSE 80

# Run Apache in the foreground
CMD ["apache2ctl", "-D", "FOREGROUND"]