#!/usr/bin/env bash
# =============================================================================
#  One-time Let's Encrypt bootstrap for the SLYK CASINO nginx gateway.
#  Solves the chicken-and-egg problem: nginx needs a cert to start :443, but
#  certbot needs nginx serving :80 to answer the http-01 challenge.
#
#  Steps:  dummy self-signed cert -> start nginx -> delete dummy ->
#          request the REAL cert via webroot -> reload nginx.
#
#  Run ONCE per domain:   ./init-letsencrypt.sh
# =============================================================================
set -euo pipefail

# Load DOMAIN / CERTBOT_EMAIL from .env, then .env.prod if present — the prod
# file wins on any key present in both, since it's the one actually driving a
# production deploy. (A stale, never-edited .env left over from local dev
# would otherwise silently override a correct DOMAIN in .env.prod here.)
set -a
[ -f .env ] && . ./.env
[ -f .env.prod ] && . ./.env.prod
set +a
: "${DOMAIN:?Set DOMAIN in .env or .env.prod}"
: "${CERTBOT_EMAIL:?Set CERTBOT_EMAIL in .env or .env.prod}"

STAGING="${STAGING:-0}"   # set STAGING=1 to test against LE staging (avoids rate limits)
LE_PATH="/etc/letsencrypt/live/$DOMAIN"

# IMPORTANT: always pin -f docker-compose.yml. Without it, `docker compose`
# auto-merges docker-compose.override.yml (the local dev stack: next dev,
# stale node_modules volumes, nginx/templates-dev with DOMAIN=localhost),
# silently breaking production nginx/cert issuance.
COMPOSE="docker compose -f docker-compose.yml"

echo "### Generating TLS dhparams into the letsencrypt volume ..."
# NOTE: this used to also curl the recommended options-ssl-nginx.conf from
# GitHub, but the certbot/certbot image has no curl (and no network
# dependency should gate cert issuance anyway) — nginx/templates now inlines
# the same ssl_protocols/ssl_ciphers directly instead of `include`-ing it.
$COMPOSE run --rm --entrypoint "/bin/sh -c '\
  openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048'" certbot

echo "### Creating a temporary self-signed cert so nginx can boot ..."
$COMPOSE run --rm --entrypoint "/bin/sh -c '\
  mkdir -p $LE_PATH && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout $LE_PATH/privkey.pem -out $LE_PATH/fullchain.pem \
    -subj \"/CN=localhost\"'" certbot

echo "### Starting nginx ..."
# --no-deps: `up -d nginx` otherwise cascades through nginx's depends_on
# (player_frontend, admin_frontend, django, erlang, which themselves depend
# on postgres/redis) and replaces an already-running prod stack — started via
# `-f docker-compose.yml -f docker-compose.prod.yml` — with the plain
# docker-compose.yml topology (different volumes, different baked domain).
# We only need nginx itself up to answer the ACME http-01 challenge.
$COMPOSE up -d --no-deps nginx

echo "### Deleting dummy cert ..."
$COMPOSE run --rm --entrypoint "/bin/sh -c 'rm -rf $LE_PATH'" certbot

echo "### Requesting the real certificate from Let's Encrypt ..."
STAGING_FLAG=""; [ "$STAGING" = "1" ] && STAGING_FLAG="--staging"
$COMPOSE run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
  $STAGING_FLAG \
  -d "$DOMAIN"

echo "### Reloading nginx with the real certificate ..."
$COMPOSE exec nginx nginx -s reload

echo "### Done. TLS is live for https://$DOMAIN"
