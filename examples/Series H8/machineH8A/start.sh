#!/bin/bash
service mysql start
service apache2 start
echo "[H8A] MySQL running (root: no password)"
echo "[H8A] phpMyAdmin at http://localhost/phpmyadmin"
exec tail -f /var/log/apache2/access.log
