# syntax=docker/dockerfile:1.7
# =============================================================================
#  SLYK CASINO — Next.js (Turborepo monorepo) production image
#  Multi-stage build: prune -> install/build -> minimal standalone runner.
#
#  Build context MUST be the monorepo ROOT (turbo prune needs the whole graph).
#  This single Dockerfile builds EITHER the Player UI or the Admin UI, selected
#  via build args:
#     APP_NAME  = pnpm workspace package name  (e.g. "web" or "admin")
#     APP_PATH  = path to the app in the repo   (e.g. "apps/web" or "apps/admin")
#
#  Example:
#     docker build -f docker/frontend.Dockerfile \
#        --build-arg APP_NAME=web --build-arg APP_PATH=apps/web \
#        --build-arg NEXT_PUBLIC_API_URL=https://slykcasino.com/api \
#        -t slyk/player-frontend .
# =============================================================================

# -----------------------------------------------------------------------------
# Base — pnpm via corepack on Node 20 Alpine
# -----------------------------------------------------------------------------
FROM node:20-alpine AS base
# libc6-compat: some native deps / Next SWC binaries expect glibc symbols on Alpine
RUN apk add --no-cache libc6-compat
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app

# -----------------------------------------------------------------------------
# Dev — hot-reload target used by docker-compose.override.yml (NOT for prod).
#   Source is bind-mounted at runtime; node_modules live in named volumes so the
#   host's (Windows) node_modules never shadow the container's Linux install.
# -----------------------------------------------------------------------------
FROM base AS dev
ENV NODE_ENV=development
# Install the FULL workspace so `next dev` has every dependency available.
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json    ./apps/web/package.json
COPY apps/admin/package.json  ./apps/admin/package.json
COPY packages/ui/package.json ./packages/ui/package.json
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile
# Fallback copy of source (the override bind-mounts the live tree over this).
COPY . .
EXPOSE 3000
# Overridden per-service in the compose override (selects web vs admin).
CMD ["pnpm", "run", "dev"]

# -----------------------------------------------------------------------------
# Pruner — isolate the target app's dependency subgraph with `turbo prune`
#   Produces /app/out/{json,full}/ + /app/out/pnpm-lock.yaml (--docker layout)
# -----------------------------------------------------------------------------
FROM base AS pruner
ARG APP_NAME
RUN pnpm add -g turbo@^2
COPY . .
RUN turbo prune "${APP_NAME}" --docker

# -----------------------------------------------------------------------------
# Installer — install pruned deps, then build only what the app needs
# -----------------------------------------------------------------------------
FROM base AS installer
ARG APP_NAME
ARG APP_PATH

# 1) Copy ONLY the pruned package.json files + lockfile first.
#    This layer is cached unless a manifest/lockfile actually changes.
COPY --from=pruner /app/out/json/ ./
COPY --from=pruner /app/out/pnpm-lock.yaml ./pnpm-lock.yaml

# Deterministic install. Cache mount keeps the pnpm store warm across builds.
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile

# 2) Copy the pruned full source for the app + its internal deps.
COPY --from=pruner /app/out/full/ ./

# 3) Build-time public env — Next.js BAKES NEXT_PUBLIC_* into the client bundle
#    at BUILD time, so these MUST be present here (not just at runtime).
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ARG NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}
ENV NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}

# Build via turbo, scoped to the target app and its upstream workspace deps.
RUN pnpm turbo run build --filter="${APP_NAME}..."

# -----------------------------------------------------------------------------
# Runner — tiny, non-root, ships only the standalone server output
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runner
ARG APP_PATH
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
# Persist APP_PATH into the runtime env so the (shell-form) CMD can resolve it.
ENV APP_PATH=${APP_PATH}

# Run as an unprivileged user (smaller attack surface).
RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# `output: 'standalone'` in a monorepo emits a self-contained tree under
# <APP_PATH>/.next/standalone that already includes the minimal node_modules
# AND the monorepo folder layout (so server.js lives at <APP_PATH>/server.js).
COPY --from=installer --chown=nextjs:nodejs /app/${APP_PATH}/.next/standalone ./
# Static assets and public/ are NOT included in standalone — copy them in place.
COPY --from=installer --chown=nextjs:nodejs /app/${APP_PATH}/.next/static ./${APP_PATH}/.next/static
COPY --from=installer --chown=nextjs:nodejs /app/${APP_PATH}/public ./${APP_PATH}/public

USER nextjs
EXPOSE 3000

# Lightweight liveness check (no curl needed — use node).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+ (process.env.PORT||3000)).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

# Shell form so ${APP_PATH} expands from the container env at runtime.
CMD node ${APP_PATH}/server.js
