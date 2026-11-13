#!/usr/bin/env bash
# =============================================================================
#  Install Mailcow next to BetBlits on the same server (run as root).
#
#    ./scripts/mailcow-install.sh                # hostname mail.$DOMAIN
#    ./scripts/mailcow-install.sh mail.example.com
#
#  Safe to re-run. It never restarts Docker or touches BetBlits containers;
#  afterwards redeploy BetBlits with -f docker-compose.mail.yml (printed at the
#  end). Settings via env: MAILCOW_DIR (/opt/mailcow-dockerized),
#  MAILCOW_TZ (Africa/Harare), MAILCOW_FORCE=1 to continue past failed checks.
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MAILCOW_DIR="${MAILCOW_DIR:-/opt/mailcow-dockerized}"
MAILCOW_TZ="${MAILCOW_TZ:-Africa/Harare}"
MAILCOW_FORCE="${MAILCOW_FORCE:-0}"
# Mailcow's own scripts treat any FORCE value as "yes to everything" — including
# rewriting /etc/docker/daemon.json and restarting Docker. Never pass it through.
unset FORCE

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
step()   { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail()   { red "✗ $*"; if [ "$MAILCOW_FORCE" = 1 ]; then yellow "  (MAILCOW_FORCE=1 — carrying on)"; else exit 1; fi; }

[ "$(id -u)" = 0 ] || { red "Run as root."; exit 1; }
docker compose version >/dev/null 2>&1 || { red "Docker Compose v2 is required."; exit 1; }

DOMAIN="$(grep -E '^DOMAIN=' "$REPO_DIR/.env.prod" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'" || true)"
MAIL_HOST="${1:-${DOMAIN:+mail.$DOMAIN}}"
[ -n "$MAIL_HOST" ] || { red "No hostname: pass one (mail.example.com) or set DOMAIN in .env.prod."; exit 1; }
case "$MAIL_HOST" in *.*.*) ;; *) red "$MAIL_HOST is not a subdomain like mail.example.com."; exit 1 ;; esac

mailcow_running() { [ -n "$(docker ps -q --filter label=com.docker.compose.project=mailcowdockerized)" ]; }

# -----------------------------------------------------------------------------
step "Checks for $MAIL_HOST"
# -----------------------------------------------------------------------------
MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
MEM_GB=$((MEM_KB / 1024 / 1024))
SKIP_CLAMD=n
if [ "$MEM_KB" -lt 3500000 ]; then
    fail "${MEM_GB} GB RAM: Mailcow plus BetBlits needs at least 4 GB free for Mailcow (8+ GB total recommended)."
    SKIP_CLAMD=y
elif [ "$MEM_KB" -lt 7500000 ]; then
    yellow "! ${MEM_GB} GB RAM — turning ClamAV (attachment virus scanning, ~1.5 GB) off. Re-enable with SKIP_CLAMD=n in mailcow.conf on a bigger box."
    SKIP_CLAMD=y
else
    green "✓ ${MEM_GB} GB RAM"
fi
free -h | sed 's/^/    /'

DISK_GB=$(df -BG --output=avail /opt 2>/dev/null | tail -1 | tr -dc 0-9)
if [ "${DISK_GB:-0}" -lt 20 ]; then yellow "! Only ${DISK_GB} GB free on /opt — mailboxes and backups need room."; else green "✓ ${DISK_GB} GB free disk"; fi

if mailcow_running; then
    green "✓ Mailcow already running — skipping port checks"
else
    BUSY=$(ss -Htlnp 2>/dev/null | awk '{print $4, $6}' \
        | grep -E '(:(25|465|587|143|993|110|995|4190)|127\.0\.0\.1:(8080|8443|13306|7654|19991)) ' || true)
    if [ -n "$BUSY" ]; then
        printf '    %s\n' "$BUSY"; fail "Ports Mailcow needs are already taken (above)."
    else
        green "✓ Mail ports free (25 465 587 143 993 110 995 4190; local 8080 8443)"
    fi
fi

CLASH=$(docker network ls -q | xargs -r docker network inspect \
    --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}' \
    | grep -v '^mailcowdockerized_' | grep -E ' 172\.22\.1\.' || true)
if [ -n "$CLASH" ]; then fail "A Docker network already uses Mailcow's subnet 172.22.1.0/24: $CLASH (set IPV4_NETWORK in mailcow.conf)"; else green "✓ Subnet 172.22.1.0/24 free"; fi

if timeout 8 bash -c '</dev/tcp/gmail-smtp-in.l.google.com/25' 2>/dev/null; then
    green "✓ Outbound port 25 open"
else
    yellow "! Can't reach port 25 outbound — the provider may block it. Mail out will fail until they unblock it (or relay through Brevo/SES/Mailgun)."
fi

PUBLIC_IP=$(curl -4fsS --max-time 8 https://api.ipify.org 2>/dev/null || true)
DNS_IP=$(getent ahostsv4 "$MAIL_HOST" 2>/dev/null | awk 'NR==1 {print $1}')
if [ -z "$DNS_IP" ]; then
    yellow "! $MAIL_HOST has no A record yet — add it (DNS only / grey cloud). Mailcow keeps a self-signed certificate until it resolves."
elif [ -n "$PUBLIC_IP" ] && [ "$DNS_IP" != "$PUBLIC_IP" ]; then
    case "$DNS_IP" in
        104.1[6-9].*|104.2[0-7].*|172.6[4-9].*|172.7[01].*|188.114.*|162.15[89].*|141.101.*|108.162.*|190.93.*|197.234.*|198.41.*|173.245.*|103.2[12].*|103.31.*)
            fail "$MAIL_HOST points at Cloudflare ($DNS_IP). Mail can't pass through Cloudflare's proxy: set that record to DNS only (grey cloud)." ;;
        *)  yellow "! $MAIL_HOST resolves to $DNS_IP, this server is $PUBLIC_IP. Fix the A record or the certificate won't issue." ;;
    esac
else
    green "✓ $MAIL_HOST → $DNS_IP"
fi

# -----------------------------------------------------------------------------
step "Mailcow code in $MAILCOW_DIR"
# -----------------------------------------------------------------------------
if [ -d "$MAILCOW_DIR/.git" ]; then
    green "✓ Already cloned"
elif [ -e "$MAILCOW_DIR" ] && [ -n "$(ls -A "$MAILCOW_DIR" 2>/dev/null)" ]; then
    red "$MAILCOW_DIR exists but isn't a Mailcow checkout."
    red "If BetBlits was started with docker-compose.mail.yml before this script, Docker created empty folders there:"
    red "  find $MAILCOW_DIR -type f | head   # if nothing is listed:  rm -rf $MAILCOW_DIR   then re-run"
    exit 1
else
    git clone https://github.com/mailcow/mailcow-dockerized "$MAILCOW_DIR"
fi
cd "$MAILCOW_DIR"

# When the host has IPv6, Mailcow's generate_config.sh / update.sh offer to edit
# /etc/docker/daemon.json and RESTART DOCKER (BetBlits down), and abort if you
# decline. Its detection only uses `ip -6 ...` and `ping -6`, so those two run
# against these stubs instead: Mailcow sees no IPv6 and configures IPv4 only.
NOIPV6="$MAILCOW_DIR/.betblits-noipv6"
mkdir -p "$NOIPV6"
printf '#!/bin/sh\n# BetBlits: hide IPv6 from Mailcow scripts (see scripts/mailcow-install.sh)\nexit 0\n' > "$NOIPV6/ip"
printf '#!/bin/sh\nexit 1\n' > "$NOIPV6/ping"
cp "$NOIPV6/ping" "$NOIPV6/ping6"
chmod 755 "$NOIPV6"/*
grep -qx '.betblits-noipv6/' .git/info/exclude 2>/dev/null || echo '.betblits-noipv6/' >> .git/info/exclude

# -----------------------------------------------------------------------------
step "mailcow.conf"
# -----------------------------------------------------------------------------
if [ -f mailcow.conf ]; then
    green "✓ Exists — keeping it (only the proxy settings below are enforced)"
else
    [ -L .env ] || ln -s mailcow.conf .env
    MAILCOW_HOSTNAME="$MAIL_HOST" MAILCOW_TZ="$MAILCOW_TZ" MAILCOW_BRANCH=master SKIP_CLAMD="$SKIP_CLAMD" \
        PATH="$NOIPV6:$PATH" ./generate_config.sh </dev/null
fi

set_conf() {
    if grep -qE "^$1=" mailcow.conf; then sed -i "s|^$1=.*|$1=$2|" mailcow.conf; else echo "$1=$2" >> mailcow.conf; fi
}
# Web side on local-only ports; BetBlits nginx terminates TLS and forwards to :8080.
set_conf HTTP_PORT 8080
set_conf HTTP_BIND 127.0.0.1
set_conf HTTPS_PORT 8443
set_conf HTTPS_BIND 127.0.0.1
# 'y' turns :8080 into a redirect-only listener — the proxy would loop.
set_conf HTTP_REDIRECT n
# IPv4 only: no Docker daemon change, and no IPv6 sending without matching reverse DNS (Gmail rejects that).
set_conf ENABLE_IPV6 false
chmod 600 mailcow.conf
grep -E '^(MAILCOW_HOSTNAME|HTTP_PORT|HTTP_BIND|HTTPS_PORT|HTTPS_BIND|HTTP_REDIRECT|ENABLE_IPV6|SKIP_CLAMD|TZ)=' mailcow.conf | sed 's/^/    /'

# -----------------------------------------------------------------------------
step "Network shared with BetBlits nginx"
# -----------------------------------------------------------------------------
docker network inspect mail-proxy >/dev/null 2>&1 || docker network create mail-proxy >/dev/null
if [ -f docker-compose.override.yml ] && ! cmp -s docker-compose.override.yml "$REPO_DIR/docker/mailcow/docker-compose.override.yml"; then
    cp docker-compose.override.yml "docker-compose.override.yml.bak.$(date +%s)"
    yellow "! Replaced an existing docker-compose.override.yml (backup kept next to it)"
fi
cp "$REPO_DIR/docker/mailcow/docker-compose.override.yml" docker-compose.override.yml
green "✓ mail-proxy network + override in place"

# -----------------------------------------------------------------------------
step "Starting Mailcow (first pull takes a few minutes)"
# -----------------------------------------------------------------------------
docker compose pull -q
docker compose up -d

printf '    waiting for certificate'
for _ in $(seq 1 60); do
    [ -s data/assets/ssl/cert.pem ] && [ -s data/assets/ssl/key.pem ] && break
    printf '.'; sleep 3
done
echo
if [ -s data/assets/ssl/cert.pem ]; then green "✓ Certificate present (self-signed until Let's Encrypt succeeds)"; else yellow "! No certificate yet — check: docker compose logs acme-mailcow"; fi

# -----------------------------------------------------------------------------
step "Certificate reload for BetBlits nginx"
# -----------------------------------------------------------------------------
PROJECT="$(basename "$REPO_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
cat > /etc/cron.d/betblits-mailcow-cert <<CRON
# Mailcow renews its certificate in place; nginx only reads it on (re)load.
23 4 * * * root docker ps -q --filter label=com.docker.compose.project=$PROJECT --filter label=com.docker.compose.service=nginx | xargs -r -I{} docker exec {} nginx -s reload >/dev/null 2>&1
CRON
chmod 644 /etc/cron.d/betblits-mailcow-cert
green "✓ /etc/cron.d/betblits-mailcow-cert (daily 04:23)"

# -----------------------------------------------------------------------------
cat <<EOF

$(green "Mailcow is running.")  Next:

1) Put the web side behind BetBlits nginx:

   cd $REPO_DIR && docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.mail.yml up -d nginx

   Keep -f docker-compose.mail.yml on every deploy from now on (without it only
   the webmail/admin site disappears; mail keeps flowing).

2) IMMEDIATELY open https://$MAIL_HOST/admin  — log in admin / moohoo,
   change that password and turn on two-factor. It is public from step 1.

3) Updating Mailcow later — always through the stubs, or its updater may
   restart Docker:

   cd $MAILCOW_DIR && env -u FORCE PATH=$NOIPV6:\$PATH ./update.sh

4) Add your mail domain (Configuration → Mail setup → Domains), create the
   mailboxes, then follow DNS in MAILCOW.md (MX, SPF, DKIM, DMARC, reverse DNS).
EOF
