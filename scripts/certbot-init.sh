#!/bin/bash
# =============================================================================
#  SLYK CASINO — Initial Let's Encrypt Certificate Issuance
#  Run this ONCE before starting nginx in production.
#  Usage: ./scripts/certbot-init.sh yourdomain.com admin@yourdomain.com
#
#  Prerequisites:
#    - DNS A record for yourdomain.com and www.yourdomain.com pointing to
#      this server
#    - Port 80 must be reachable from the internet (nginx already running
#      with the HTTP-only config so certbot can complete the http-01 challenge)
# =============================================================================

set -euo pipefail

DOMAIN=${1:?Usage: $0 <domain> <email>}
EMAIL=${2:?Usage: $0 <domain> <email>}

echo "==> Requesting certificate for ${DOMAIN} and www.${DOMAIN}..."

docker run --rm \
  -v ./nginx/certbot/conf:/etc/letsencrypt \
  -v ./nginx/certbot/www:/var/www/certbot \
  certbot/certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

echo "==> Certificate issued successfully. Restart nginx to pick it up:"
echo "    docker compose -f docker-compose.prod.yml restart nginx"
