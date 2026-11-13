#!/bin/sh
# Runs from nginx's /docker-entrypoint.d on every start (docker-compose.mail.yml).
# Turns the mail.* proxy on only when Mailcow's certificate is present: if Mailcow
# is missing, stopped mid-install or removed, BetBlits still boots without it.
set -eu
SSL=/etc/nginx/mailcow/ssl
if [ -s "$SSL/cert.pem" ] && [ -s "$SSL/key.pem" ]; then
    cp /etc/nginx/mailcow/mailcow.conf /etc/nginx/conf.d/mailcow.conf
    echo "40-mailcow: forwarding mail.* to Mailcow"
else
    rm -f /etc/nginx/conf.d/mailcow.conf
    echo "40-mailcow: no Mailcow certificate in $SSL - mail proxy left off"
fi
