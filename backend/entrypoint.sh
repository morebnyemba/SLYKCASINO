#!/usr/bin/env sh
set -e

echo "[entrypoint] applying migrations…"
python manage.py migrate --noinput

echo "[entrypoint] collecting static files…"
python manage.py collectstatic --noinput

# Optional: auto-create a superuser from env on first boot (raw-DB admin access).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "[entrypoint] ensuring superuser '$DJANGO_SUPERUSER_USERNAME'…"
  python manage.py createsuperuser --noinput || true
fi

echo "[entrypoint] starting gunicorn on :8000…"
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --access-logfile - \
  --error-logfile -
