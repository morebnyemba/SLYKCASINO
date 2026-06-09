#!/bin/bash
# =============================================================================
#  SLYK CASINO — Production Deploy Script
#  Usage: ./scripts/deploy.sh
#  Requires: .env.prod present in the repo root
# =============================================================================

set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> [1/6] Building / pulling latest images..."
$COMPOSE build

echo "==> [2/6] Running database migrations..."
$COMPOSE run --rm django python manage.py migrate

echo "==> [3/6] Collecting static files..."
$COMPOSE run --rm django python manage.py collectstatic --noinput

echo "==> [4/6] Seeding demo data..."
$COMPOSE run --rm django python manage.py seed_demo

echo "==> [5/6] Starting / restarting services..."
$COMPOSE up -d

echo "==> [6/6] Recent logs (last 50 lines)..."
$COMPOSE logs --tail=50
