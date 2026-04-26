<?php
/**
 * Drupal 7 CLI installer script.
 * Runs the Drupal installation programmatically to populate the DB.
 */

$_SERVER['HTTP_HOST']   = 'localhost';
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
$_SERVER['REQUEST_URI'] = '/';
$_SERVER['REQUEST_METHOD'] = 'GET';

define('DRUPAL_ROOT', '/var/www/html');
chdir(DRUPAL_ROOT);

require_once DRUPAL_ROOT . '/includes/install.core.inc';

$settings = array(
  'interactive' => FALSE,
  'parameters'  => array(
    'profile'  => 'standard',
    'locale'   => 'en',
  ),
  'forms' => array(
    'install_settings_form' => array(
      'driver'   => 'mysql',
      'mysql'    => array(
        'database' => 'drupal',
        'username' => 'drupal',
        'password' => 'drupal123',
        'host'     => 'localhost',
        'port'     => '',
        'prefix'   => '',
        'advanced_options' => array(),
      ),
    ),
    'install_configure_form' => array(
      'site_name'            => 'KoTH H3B - Drupal',
      'site_mail'            => 'admin@koth.local',
      'account'              => array(
        'name' => 'admin',
        'mail' => 'admin@koth.local',
        'pass' => array('pass1' => 'admin123', 'pass2' => 'admin123'),
      ),
      'date_default_timezone' => 'UTC',
      'update_status_module'  => array(1 => 0, 2 => 0),
    ),
  ),
);

try {
    install_drupal($settings);
    echo "Drupal installation completed successfully.\n";
} catch (Exception $e) {
    echo "Install error: " . $e->getMessage() . "\n";
    exit(1);
}
