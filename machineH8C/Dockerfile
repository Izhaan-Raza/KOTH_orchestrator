FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install all required PHP packages and tools in one go
RUN apt-get update && apt-get install -y \
    php8.1 \
    php8.1-cli \
    php8.1-common \
    php8.1-curl \
    php8.1-mbstring \
    php8.1-xml \
    php8.1-zip \
    php8.1-mysql \
    php8.1-sqlite3 \
    php8.1-bcmath \
    php8.1-tokenizer \
    php8.1-dom \
    composer \
    curl \
    wget \
    unzip \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Create king file for SLA bot
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 666 /root/king.txt && chmod 777 /root

# Create laravel user
RUN useradd -m -s /bin/bash laraveluser && echo 'laraveluser:laravel123' | chpasswd

# SUID bash for privilege escalation
RUN cp /bin/bash /bin/bash_suid && chmod u+s /bin/bash_suid

COPY php.ini /etc/php/8.1/cli/conf.d/99-custom.ini

# Create Laravel project (vulnerable version)
WORKDIR /opt
RUN composer create-project laravel/laravel=8.4.2 laravel --prefer-dist --no-interaction
WORKDIR /opt/laravel

# Install vulnerable Ignition (CVE-2021-3129)
RUN composer require facade/ignition=2.5.1 --no-interaction

# Configure .env for debug mode
RUN cp .env.example .env && \
    sed -i 's/APP_DEBUG=false/APP_DEBUG=true/' .env && \
    sed -i 's/APP_ENV=local/APP_ENV=local/' .env

# Generate application key
RUN php artisan key:generate

# Set permissions for storage and cache
RUN chown -R laraveluser:laraveluser /opt/laravel/storage /opt/laravel/bootstrap/cache && \
    chmod -R 775 /opt/laravel/storage /opt/laravel/bootstrap/cache

# Copy start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000 9999

CMD ["/start.sh"]
