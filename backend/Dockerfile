# =============================================================================
#  SLYK CASINO — Django backend (REST API + /django-admin raw-DB intervention)
#  Internal service on :8000, reached via nginx /api/ and /django-admin/.
# =============================================================================
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg[binary] needs no build deps; keep the image lean.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Run as non-root.
RUN addgroup --system django && adduser --system --ingroup django django \
 && chmod +x entrypoint.sh \
 && mkdir -p /app/staticfiles && chown -R django:django /app
USER django

EXPOSE 8000

# migrate + collectstatic + gunicorn (see entrypoint.sh)
CMD ["./entrypoint.sh"]
