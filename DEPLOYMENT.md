# SLYK CASINO — Containerized Platform

A pnpm + Turborepo monorepo (Next.js Player + Admin UIs) plus a Django REST
backend and an Erlang/Cowboy realtime engine, all fronted by an Nginx API
gateway with Let's Encrypt TLS.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | **Next.js 16** (Turbopack) · **React 19** · **TypeScript** · **Tailwind v4** · **shadcn/ui** |
| Monorepo | pnpm workspaces + **Turborepo** (`turbo prune` per-app Docker builds) |
| Backend API | **Django 5.1 + DRF** (gunicorn, WhiteNoise for admin static) |
| Realtime | **Erlang/OTP 27 + Cowboy 2.12** WebSocket (`pg` pub/sub) |
| Gateway | **Nginx** (envsubst templates) + **certbot** (ACME) |
| Data | Postgres 16 · Redis 7 |

## Files

| Path | Purpose |
|------|---------|
| `docker/frontend.Dockerfile` | Multi-stage Next image: `turbo prune` → build → standalone runner (+ a `dev` target). Builds both apps via build args. |
| `docker-compose.yml` | Master prod topology. Only **nginx** is host-exposed. |
| `docker-compose.override.yml` | Local dev (auto-merged): hot-reload, HTTP-only nginx, certbot off. |
| `nginx/templates/default.conf.template` | Prod gateway routing (TLS). `templates-dev/` is the HTTP-only dev variant. |
| `init-letsencrypt.sh` | One-time Let's Encrypt bootstrap. |
| `backend/` | Django project (`config/`) + `core` app (models, DRF API, admin). |
| `realtime/` | Erlang release (`rebar3`) with the Cowboy WebSocket handler. |

## Monorepo layout

```text
.
├─ apps/
│  ├─ web/      → Player UI   (pkg "web";  src/app, basePath: /)
│  └─ admin/    → Admin UI    (pkg "admin"; src/app, basePath: /admin-portal)
├─ packages/
│  └─ ui/       → @slyk/ui — shared shadcn/ui components + Tailwind v4 theme
├─ backend/     → Django REST API + /django-admin
├─ realtime/    → Erlang/Cowboy WebSocket engine
├─ pnpm-workspace.yaml · turbo.json · package.json (packageManager: pnpm@…)
```

Each app: `src/app` (App Router, `.tsx`), `next.config.ts`, `postcss.config.mjs`,
`src/app/globals.css` (imports `@slyk/ui/globals.css`). The shared UI package is
compiled into each app via `transpilePackages: ['@slyk/ui']`.

## Frontend specifics

- **Standalone output** (both apps) for tiny runner images: `output: 'standalone'`
  with `outputFileTracingRoot` pinned to the repo root (monorepo tracing).
- **Admin `basePath: '/admin-portal'`** (+ `assetPrefix`) so its `/_next/*` assets
  don't collide with the Player app on the shared domain. Verified: admin `/`
  returns 404, `/admin-portal` and `/admin-portal/_next/*` return 200.
- **`NEXT_PUBLIC_*` are baked at BUILD time** → passed as Docker **build args**
  (derived from `DOMAIN` in compose), not runtime env. Changing the domain
  requires a **rebuild**. In dev they're runtime envs the dev server reads live.
- Each app keeps a `public/.gitkeep` so the Dockerfile `COPY public/` succeeds.

## Backends

- **Django** (`backend/`): REST API under `/api/` (events, bets, promotions,
  players, chat + `wallet/`, `admin/stats/`, `players/me/`, `health/`) and the
  admin under `/django-admin/`. Container entrypoint runs `migrate` +
  `collectstatic` + gunicorn; WhiteNoise serves admin static at `/django-static/`.
  Set `DJANGO_SUPERUSER_*` to auto-create the raw-DB superuser on first boot.
- **Erlang** (`realtime/`): Cowboy listener on `:8080`; `/ws/<channel>` upgrades
  to a WebSocket and joins a `pg` group named after the channel (e.g. `odds`,
  `chat:lobby`, `admin:bets`). Inbound frames fan out to all sockets on the
  channel. `/health` returns 200.

## Routing (Nginx)

| Path | Upstream |
|------|----------|
| `/` | `player_frontend:3000` (Next.js Player) |
| `/admin-portal` | `admin_frontend:3000` (Next.js Admin, basePath) |
| `/api/` | `django:8000` (DRF REST) |
| `/django-admin/` | `django:8000` (raw DB admin) |
| `/django-static/` | `django:8000` (WhiteNoise admin assets) |
| `/ws/` | `erlang:8080` (WebSocket, `Upgrade` headers passed) |
| `/.well-known/acme-challenge/` | certbot webroot |

## Network security

Frontend and backend services declare **no `ports:`** — only `expose:`. They are
unreachable from the host and accept traffic solely over the internal `edge`
network via nginx. Only nginx publishes `80:80` and `443:443`.

---

## Local development (hot reload, HTTP, no TLS)

`docker-compose.override.yml` is auto-merged by `docker compose`, so a plain
`up` gives you the dev stack: frontends run `next dev` (the Dockerfile `dev`
target), source is bind-mounted, and nginx serves HTTP on `:80` with no certbot.

```bash
cp .env.example .env          # DOMAIN can stay as-is; nginx uses localhost in dev
docker compose up             # builds dev images, starts everything

# Access:
#   http://localhost/                 -> Player UI   (also direct: http://localhost:3000)
#   http://localhost/admin-portal     -> Admin UI    (also direct: http://localhost:3001/admin-portal)
#   http://localhost/api/ , /ws/ , /django-admin/  -> backends
```

Notes:
- `node_modules` are kept in **named volumes** so the host's Windows install never
  shadows the container's Linux one. After changing dependencies, rebuild:
  `docker compose build player_frontend admin_frontend`.
- In dev, `NEXT_PUBLIC_*` are **runtime** envs (the dev server reads them live);
  in prod they are **baked at build time**.

---

## Deploy sequence (⏸ awaiting your approval before running)

> **IMPORTANT:** pass `-f docker-compose.yml` so the dev override is NOT merged.

```bash
cp .env.example .env          # then edit DOMAIN, CERTBOT_EMAIL, POSTGRES_*

# 1) Build images (NEXT_PUBLIC_* baked from DOMAIN)
docker compose -f docker-compose.yml build

# 2) Bring up datastores + backends + frontends (not nginx yet)
docker compose -f docker-compose.yml up -d postgres redis django erlang player_frontend admin_frontend

# 3) First-time TLS issuance (starts nginx, gets the cert, reloads)
chmod +x init-letsencrypt.sh
STAGING=1 ./init-letsencrypt.sh      # test first; rerun without STAGING for prod

# 4) Full stack up (nginx + certbot renewal loop)
docker compose -f docker-compose.yml up -d
```

> Tip: `init-letsencrypt.sh` also runs `docker compose` internally — export
> `COMPOSE_FILE=docker-compose.yml` first so it too ignores the dev override.

> Point `DOMAIN`'s A/AAAA record at this host **before** step 3 — Let's Encrypt
> validates over the public internet on port 80.
