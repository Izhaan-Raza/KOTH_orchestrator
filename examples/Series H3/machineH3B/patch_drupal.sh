#!/bin/bash
# Patch Drupal 7's MySQL driver to remove NO_AUTO_CREATE_USER from sql_mode
# This mode was removed in MySQL 8.0 but Drupal 7.57 hardcodes it
set -e

DBFILE="/var/www/html/includes/database/mysql/database.inc"

if grep -q "NO_AUTO_CREATE_USER" "$DBFILE"; then
    sed -i "s/NO_AUTO_CREATE_USER,//g" "$DBFILE"
    sed -i "s/,NO_AUTO_CREATE_USER//g" "$DBFILE"
    sed -i "s/'NO_AUTO_CREATE_USER'//g" "$DBFILE"
    echo "Patched: removed NO_AUTO_CREATE_USER from $DBFILE"
else
    echo "NO_AUTO_CREATE_USER not found in $DBFILE (already patched or different version)"
fi
