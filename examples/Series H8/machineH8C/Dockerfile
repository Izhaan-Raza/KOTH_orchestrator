FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    php \
    php-cli \
    php-xml \
    php-mbstring \
    php-curl \
    php-zip \
    python3 \
    composer \
    curl \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create laravel user
RUN useradd -m -s /bin/bash laraveluser && echo 'laraveluser:laravel123' | chpasswd

# PrivEsc: SUID bash available (bash -p gives root)
RUN cp /bin/bash /bin/bash_suid && chmod u+s /bin/bash_suid

# Deploy Laravel 8.4.2 (vulnerable to CVE-2021-3129 debug mode RCE)
RUN mkdir -p /opt/laravel
COPY app/ /opt/laravel/
RUN chown -R laraveluser:laraveluser /opt/laravel/

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000

CMD ["/start.sh"]
