<?php
// phpMyAdmin configuration - root with no password
$cfg['blowfish_secret'] = 'koth_phpmyadmin_secret_key_32chars!';
$cfg['Servers'][1]['auth_type'] = 'config';
$cfg['Servers'][1]['host'] = 'localhost';
$cfg['Servers'][1]['user'] = 'root';
$cfg['Servers'][1]['password'] = '';  // No password!
$cfg['Servers'][1]['AllowNoPassword'] = true;
$cfg['Servers'][1]['connect_type'] = 'socket';
$cfg['LoginCookieValidity'] = 1440;
