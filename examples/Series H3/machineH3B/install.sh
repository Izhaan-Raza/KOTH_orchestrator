#!/bin/bash
set -e

service mysql start
sleep 5

mysql -e "CREATE DATABASE IF NOT EXISTS drupal;"
mysql -e "CREATE USER IF NOT EXISTS 'drupal'@'localhost' IDENTIFIED BY 'drupal123';"
mysql -e "GRANT ALL ON drupal.* TO 'drupal'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# Run Drupal 7 installer via PHP CLI
php /var/www/html/scripts/drupal.sh \
    --root=/var/www/html \
    --db-url=mysql://drupal:drupal123@localhost/drupal \
    --account-name=admin \
    --account-pass=admin123 \
    --site-name="KoTH H3B" 2>&1 || true

# Alternatively use drush-style table import approach
if ! mysql -u drupal -pdrupal123 drupal -e "SHOW TABLES;" 2>/dev/null | grep -q users; then
    echo "Manual schema import fallback..."
    mysql -u drupal -pdrupal123 drupal < /tmp/drupal_schema.sql 2>/dev/null || true
fi

echo "DB setup complete"
