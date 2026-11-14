# Mailcow next to BetBlits

Mailcow (a full mail server: Postfix, Dovecot, SOGo webmail, Rspamd) runs on the same
server as BetBlits, as its own Docker Compose project in `/opt/mailcow-dockerized`.

```
             :80/:443                                    :25 465 587 143 993 110 995 4190
                │                                                    │
   ┌────────────▼─────────────┐   mail-proxy network   ┌─────────────▼──────────────┐
   │ BetBlits nginx           │ ─────────────────────▶ │ Mailcow (own compose       │
   │  yourdomain.com → casino │   mail.* / autodiscover│  project, own networks)    │
   │  mail.*  → nginx-mailcow │   .* / autoconfig.*    │  nginx-mailcow :8080 (HTTP)│
   └──────────────────────────┘                        └────────────────────────────┘
```

- BetBlits keeps ports 80/443. Mailcow's web side listens on `127.0.0.1:8080`/`8443` only,
  and BetBlits nginx forwards `mail.*`, `autodiscover.*` and `autoconfig.*` to it over a small
  shared network (`mail-proxy`) that holds just the two nginx containers. BetBlits can't reach
  Mailcow's database, and Mailcow can't reach BetBlits.
- Mail ports go straight to Mailcow; they never pass through BetBlits.
- The certificate for `mail.*` is Mailcow's own: its ACME client issues and renews it, and
  BetBlits nginx forwards the challenges to it. A daily cron reloads BetBlits nginx to
  pick up renewals.
- If Mailcow is missing or broken, BetBlits still starts: `nginx/mail/40-mailcow.sh` only turns
  the mail proxy on when Mailcow's certificate exists.

Files: `docker-compose.mail.yml`, `nginx/mail/`, `docker/mailcow/docker-compose.override.yml`,
`scripts/mailcow-install.sh`.

## Read this first

- **Memory.** Mailcow uses about 3 GB, plus about 1.5 GB more with ClamAV. Check `free -h`
  next to the running casino. Below about 8 GB in total, the script turns ClamAV off.
- **Transactional email (sign-up, password reset).** Deliverability depends on the server
  IP's reputation, and many VPS ranges start out flagged. A fresh mail server also has no
  sending history. For mail that players must receive, consider relaying Mailcow's outbound
  mail through Brevo, SES or Mailgun (in Mailcow: *Configuration → Routing → Sender-dependent
  transports*). Mailcow then still owns the mailboxes.
- **Spamhaus.** If the script's ASN check says that your provider's network is blocked from
  Spamhaus' public lists, create a free Spamhaus DQS key and put it in `SPAMHAUS_DQS_KEY` in
  `mailcow.conf`. Without it, spam filtering is weaker.

## Install

### 1. DNS: the mail host first

Add an A record for `mail.yourdomain.com` pointing to the server IP. It must be **DNS only**
(grey cloud in Cloudflare): mail can't pass through Cloudflare's proxy. Don't add an AAAA
record, because Mailcow is set up for IPv4 only (see below).

Set **reverse DNS (PTR)** for the server IP to `mail.yourdomain.com` in your provider's control
panel. Gmail and Outlook penalise mail from an IP whose PTR doesn't match.

### 2. Run the installer (as root, from the BetBlits checkout)

```bash
cd ~/betblits && git pull && ./scripts/mailcow-install.sh
```

The installer:

- checks RAM, disk, free ports, the Docker subnet, outbound port 25 and DNS;
- clones Mailcow and generates `mailcow.conf`;
- sets the web side to local-only ports, sets `HTTP_REDIRECT=n` and `ENABLE_IPV6=false`;
- creates the `mail-proxy` network, starts Mailcow and installs the certificate-reload cron.

It is safe to re-run, and it never restarts Docker or touches BetBlits.

Mailcow is IPv4 only on purpose:

- When the host has IPv6, Mailcow's own setup offers to rewrite `/etc/docker/daemon.json` and
  **restart Docker**, which would take the casino down. If you decline, it aborts. The
  installer hides IPv6 from that one step.
- Sending over IPv6 without matching reverse DNS gets mail rejected anyway.

### 3. Put the web side behind BetBlits nginx

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.mail.yml up -d --build
```

From now on, **add `-f docker-compose.mail.yml` to every deploy**. If you forget it, only the
webmail and admin site go away; mail keeps flowing.

Check it works:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.mail.yml logs nginx | grep 40-mailcow
```

### 4. Lock down the admin straight away

Open `https://mail.yourdomain.com/admin`. The first login is `admin` / `moohoo`, and the page
is public from step 3. Change the password and turn on two-factor authentication.

### 5. Domain and mailboxes

1. *Configuration → Mail setup → Domains → Add domain*: `yourdomain.com`.
2. Add mailboxes, for example:
   - `noreply@` for the app;
   - `support@` for players;
   - `dmarc@` for reports.

### 6. DNS records for the domain

Mailcow lists the exact values under *Configuration → Mail setup → Domains → DNS*.

| Type  | Name                        | Value                                          |
|-------|-----------------------------|------------------------------------------------|
| MX    | `yourdomain.com`            | `mail.yourdomain.com` (priority 10)            |
| TXT   | `yourdomain.com`            | `v=spf1 mx a -all` (add `include:` for any relay) |
| TXT   | `dkim._domainkey`           | From *Configuration → ARC/DKIM keys*: 2048-bit key for the domain |
| TXT   | `_dmarc`                    | `v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com` |
| CNAME | `autodiscover`              | `mail.yourdomain.com` (DNS only)               |
| CNAME | `autoconfig`                | `mail.yourdomain.com` (DNS only)               |
| SRV   | `_autodiscover._tcp`        | `0 1 443 mail.yourdomain.com`                  |

Start DMARC at `p=none` for a week if other services send as your domain. Once the reports
are clean, raise it to `quarantine`.

After adding the CNAMEs, Mailcow adds them to its certificate by itself, within about an hour.

### 7. Point BetBlits at it (`.env.prod`)

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mail.yourdomain.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=noreply@yourdomain.com
EMAIL_HOST_PASSWORD=<the mailbox password>
DEFAULT_FROM_EMAIL=BetBlits <noreply@yourdomain.com>
```

Redeploy, then send yourself a password reset. Score a test mail at mail-tester.com and aim
for 9/10 or better.

## Running it

- **Updates.** Always run updates through the IPv6 stubs, or the updater may restart Docker:
  ```bash
  cd /opt/mailcow-dockerized && env -u FORCE PATH=/opt/mailcow-dockerized/.betblits-noipv6:$PATH ./update.sh
  ```
- **Backups.** `/opt/mailcow-dockerized/helper-scripts/backup_and_restore.sh backup all`, run
  from cron and copied off the server. Mailboxes aren't in the BetBlits backups.
- **Logs.** `cd /opt/mailcow-dockerized && docker compose logs --tail=100 postfix-mailcow`
  (or `acme-mailcow`, `nginx-mailcow`).
- **Certificate not issuing.** Run `docker compose logs acme-mailcow` in the Mailcow folder.
  The usual cause is the A record pointing elsewhere or being proxied by Cloudflare.

## Remove

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d nginx
```

```bash
cd /opt/mailcow-dockerized && docker compose down
```

```bash
rm /etc/cron.d/betblits-mailcow-cert && docker network rm mail-proxy
```

Keep `/opt/mailcow-dockerized` until you've taken the mail out of it.
