#!/bin/bash
set -e

echo "[*] Starting MySQL..."
service mysql start
sleep 5

echo "[*] Configuring Database..."
mysql -e "CREATE DATABASE wordpress;"
mysql -e "CREATE USER 'wpuser'@'localhost' IDENTIFIED BY 'wppassword';"
mysql -e "GRANT ALL PRIVILEGES ON wordpress.* TO 'wpuser'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

echo "[*] Downloading WordPress..."
cd /var/www/html
rm -f index.html
curl -4 -L --progress-bar https://wordpress.org/wordpress-5.7.tar.gz -o /tmp/wp.tar.gz
tar -xzf /tmp/wp.tar.gz -C /var/www/html --strip-components=1
rm /tmp/wp.tar.gz

echo "[*] Configuring wp-config.php..."
cp wp-config-sample.php wp-config.php
sed -i "s/database_name_here/wordpress/" wp-config.php
sed -i "s/username_here/wpuser/" wp-config.php
sed -i "s/password_here/wppassword/" wp-config.php
chown -R www-data:www-data /var/www/html/

echo "[*] Injecting Vulnerable Plugin..."
mkdir -p /var/www/html/wp-content/plugins/reflex-gallery
cat > /var/www/html/wp-content/plugins/reflex-gallery/reflex-gallery.php << 'PLUGIN'
<?php
/**
 * Plugin Name: Reflex Gallery
 * Version: 3.1.3
 */
// Intentionally vulnerable upload handler
if (isset($_POST['action']) && $_POST['action'] === 'UploadHandler') {
    // Hardcoded absolute path to bypass PHP 8 fatal error on undefined WP_CONTENT_DIR
    $upload_dir = '/var/www/html/wp-content/uploads/';
    if (!is_dir($upload_dir)) mkdir($upload_dir, 0755, true);
    $file = $_FILES['file'];
    move_uploaded_file($file['tmp_name'], $upload_dir . basename($file['name']));
    echo json_encode(['status' => 'success', 'file' => '/wp-content/uploads/' . basename($file['name'])]);
    exit;
}
PLUGIN
chown -R www-data:www-data /var/www/html/wp-content/

echo "[*] Downloading WP-CLI..."
curl -4 -sO https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar

echo "[*] Installing WordPress Core..."
php wp-cli.phar core install \
    --url=http://localhost \
    --title="KoTH Blog" \
    --admin_user=admin \
    --admin_password=admin123 \
    --admin_email=admin@koth.local \
    --allow-root

echo "[*] Activating Vulnerable Plugin..."
php wp-cli.phar plugin activate reflex-gallery --allow-root

echo "[*] Setting Privilege Escalation Vector..."
chmod u+s /usr/bin/find

echo "[*] Finalizing permissions for web root..."
chown -R www-data:www-data /var/www/html/

echo "[*] Cleaning up database locks for Docker image snapshot..."
service mysql stop
sleep 2

echo "[H1A] Build script complete."