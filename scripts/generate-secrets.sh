#!/bin/bash
# =============================================================================
#  SLYK CASINO — Generate secure values for an env file
#  Usage: ./scripts/generate-secrets.sh [.env.prod|.env]  (default: .env.prod)
#
#  Creates the target from its matching .env.*.example if it doesn't exist
#  yet, then replaces only the fields still holding their example placeholder
#  ("change-me*") with freshly generated random values. Never touches a
#  value you've already customized, so it's safe to re-run.
# =============================================================================
set -euo pipefail

TARGET=${1:-.env.prod}
EXAMPLE="${TARGET}.example"

if [ ! -f "$EXAMPLE" ]; then
  echo "No template found at $EXAMPLE" >&2
  exit 1
fi

if [ ! -f "$TARGET" ]; then
  echo "==> $TARGET doesn't exist yet — creating it from $EXAMPLE"
  cp "$EXAMPLE" "$TARGET"
fi

gen_secret() {
  # `head -c` closes the pipe early, SIGPIPE-ing `tr`; under pipefail that
  # would otherwise propagate as a failure through $(...) and, with set -e,
  # abort the whole script after the very first secret. Swallow it here.
  LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "${1:-50}" || true
}

# key -> generated length
declare -A SECRETS=(
  [POSTGRES_PASSWORD]=32
  [DJANGO_SECRET_KEY]=64
  [DJANGO_SUPERUSER_PASSWORD]=32
)

CHANGED=()
for key in "${!SECRETS[@]}"; do
  current=$(grep -E "^${key}=" "$TARGET" | head -1 | cut -d= -f2-)
  if [ -z "$current" ] || [[ "$current" == change-me* ]]; then
    new_value=$(gen_secret "${SECRETS[$key]}")
    sed -i "s|^${key}=.*|${key}=${new_value}|" "$TARGET"
    CHANGED+=("${key}=${new_value}")
  fi
done

chmod 600 "$TARGET"

if [ "${#CHANGED[@]}" -eq 0 ]; then
  echo "==> Nothing to generate — $TARGET already has custom secrets set."
else
  echo "==> Generated secure values in $TARGET for:"
  for c in "${CHANGED[@]}"; do
    echo "    - ${c%%=*}"
  done
  superuser_line=$(printf '%s\n' "${CHANGED[@]}" | grep '^DJANGO_SUPERUSER_PASSWORD=' || true)
  if [ -n "$superuser_line" ]; then
    echo
    echo "    Superuser password (save this now — it won't be shown again):"
    echo "    ${superuser_line#DJANGO_SUPERUSER_PASSWORD=}"
  fi
fi

echo
echo "==> Not auto-generated — review/edit these in $TARGET manually:"
grep -E '^(DOMAIN|CERTBOT_EMAIL|DJANGO_ALLOWED_HOSTS|DJANGO_CSRF_TRUSTED_ORIGINS|CORS_ALLOWED_ORIGINS|DJANGO_SUPERUSER_USERNAME|DJANGO_SUPERUSER_EMAIL|EMAIL_HOST_USER|EMAIL_HOST_PASSWORD|DEFAULT_FROM_EMAIL|FRONTEND_URL|API_FOOTBALL_KEY)=' "$TARGET" | sed 's/^/    /'
