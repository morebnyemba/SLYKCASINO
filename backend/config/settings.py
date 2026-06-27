"""Django settings for the SLYK Casino backend."""
import os
from datetime import datetime, timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-insecure-change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', 'false').lower() == 'true'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,django').split(',')
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://localhost').split(',') if o
]

DJANGO_APPS = [
    'jazzmin',  # must precede django.contrib.admin to override its templates
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_celery_beat',
]

# Domain apps (bounded contexts). Order: identity -> ledger -> domains.
DOMAIN_APPS = [
    'apps.accounts',
    'apps.wallet',
    'apps.sportsbook',
    'apps.casino',
    'apps.promotions',
    'apps.livechat',
    'apps.notifications',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + DOMAIN_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'config.middleware.GeoBlockMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise serves /django-static/ (admin CSS/JS) straight from gunicorn,
    # so the Django admin is styled without extra nginx static routing.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Postgres via DATABASE_URL; falls back to local sqlite for quick scaffolding.
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "db.sqlite3"}'),
        conn_max_age=600,
    )
}

# Served behind the nginx gateway under /django-admin/ — keep the admin there too.
# (The REST API mounts at the root of this service and is exposed via nginx /api/.)

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/minute',
        'user': '300/minute',
        'auth': '10/minute',   # used explicitly on auth endpoints
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'TOKEN_OBTAIN_SERIALIZER': 'apps.accounts.serializers.CustomTokenObtainPairSerializer',
}

CORS_ALLOWED_ORIGINS = [
    o for o in os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost').split(',') if o
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/django-static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# KYC documents and other uploads. Never served as static files — access goes
# through admin-gated API views only (apps.accounts.views.AdminKYCViewSet.document),
# since nginx only proxies /api/ and /django-admin/ to this service.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

BLOCKED_COUNTRIES = os.environ.get('BLOCKED_COUNTRIES', 'US,FR,AU,SG,HK').split(',')

# ---------------------------------------------------------------------------
# Realtime engine (Erlang) — internal HTTP ingest used to fan out live odds and
# chat. Disabled by default so dev/test never block on the network; enable in
# production where the engine is reachable on the compose network.
# ---------------------------------------------------------------------------
REALTIME_PUBLISH_ENABLED = os.environ.get('REALTIME_PUBLISH_ENABLED', 'false').lower() == 'true'
REALTIME_PUBLISH_URL = os.environ.get('REALTIME_PUBLISH_URL', 'http://erlang:8080/publish')
# Calls to the engine (publish + admin WebSocket tickets, see
# common.realtime_auth) are authenticated with SECRET_KEY — the erlang
# container is given the same value via REALTIME_SHARED_SECRET in
# docker-compose*.yml, so no separate credential needs provisioning.

# --- api-football.com (https://www.api-football.com/documentation-v3) ---
# Unset by default: ApiFootballClient no-ops (returns []) without a key, so
# dev/test never hits the network.
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')
API_FOOTBALL_BASE_URL = os.environ.get('API_FOOTBALL_BASE_URL', 'https://v3.football.api-sports.io')
# League IDs to import upcoming fixtures/events for (see api-football's
# /leagues endpoint for IDs, e.g. 39 = English Premier League). Comma-
# separated; empty by default, in which case the import task auto-discovers
# and imports every league api-football currently has an active season for
# (see ApiFootballClient.fetch_leagues / services.import_all_current_leagues)
# — set this to opt back into a curated subset and bound API quota usage.
API_FOOTBALL_LEAGUES = [
    int(v) for v in os.environ.get('API_FOOTBALL_LEAGUES', '').split(',') if v.strip()
]
# api-football "season" is the year a league's season started (e.g. a
# 2024-25 European league is season=2024). Defaults to the current year;
# override per-deployment if your leagues' season numbering differs. Only
# used for the manually-curated API_FOOTBALL_LEAGUES path — auto-discovery
# uses each league's own current season year instead.
API_FOOTBALL_SEASON = int(os.environ.get('API_FOOTBALL_SEASON', str(datetime.now().year)))
# How many of each configured league's next upcoming fixtures to import per run.
API_FOOTBALL_IMPORT_NEXT = int(os.environ.get('API_FOOTBALL_IMPORT_NEXT', '20'))

# ---------------------------------------------------------------------------
# Celery — workers run domain recovery; beat schedules reconciliation passes.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/1')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/2')
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 300

# Periodic reconciliation. Each manager is idempotent, so cadence is a safety
# knob, not a correctness one — running more often just narrows drift windows.
CELERY_BEAT_SCHEDULE = {
    'wallet-reconcile-ledger': {
        'task': 'apps.wallet.tasks.reconcile_ledger',
        'schedule': 300.0,   # every 5 min
    },
    'sportsbook-orphaned-bets': {
        'task': 'apps.sportsbook.tasks.reconcile_orphaned_bets',
        'schedule': 600.0,
    },
    'sportsbook-sync-live-fixtures': {
        'task': 'apps.sportsbook.tasks.sync_live_fixtures',
        'schedule': 60.0,
    },
    'sportsbook-sync-fixture-odds': {
        'task': 'apps.sportsbook.tasks.sync_fixture_odds',
        'schedule': 300.0,
    },
    'sportsbook-import-upcoming-fixtures': {
        'task': 'apps.sportsbook.tasks.import_upcoming_fixtures',
        # Every 30 min. Imports API_FOOTBALL_LEAGUES if set, else auto-discovers
        # every currently-active league — no-op either way if API_FOOTBALL_KEY
        # is unset.
        'schedule': 1800.0,
    },
    'casino-retry-debits': {
        'task': 'apps.casino.tasks.reconcile_debit_sequences',
        'schedule': 600.0,
    },
    'promotions-reconcile-wagering': {
        'task': 'apps.promotions.tasks.reconcile_wagering',
        'schedule': 900.0,
    },
    'accounts-reconcile-kyc': {
        'task': 'apps.accounts.tasks.reconcile_kyc',
        'schedule': 3600.0,
    },
    'accounts-lift-exclusions': {
        'task': 'apps.accounts.tasks.lift_expired_exclusions',
        'schedule': 3600.0,
    },
    'notifications-expiring-promos': {
        'task': 'apps.notifications.tasks.notify_expiring_promos',
        'schedule': 86400.0,  # daily
    },
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@slyk.casino')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Domain logging (recovery managers log under recovery.<domain>).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'recovery': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}

# ---------------------------------------------------------------------------
# Payment & KYC provider selection
# ---------------------------------------------------------------------------
PSP_PROVIDER = os.environ.get('PSP_PROVIDER', 'stub')
KYC_PROVIDER = os.environ.get('KYC_PROVIDER', 'stub')

# ---------------------------------------------------------------------------
# Django admin theming (django-jazzmin) — matches the SLYK gold/indigo brand
# used across apps/admin and apps/web, so /django-admin/ doesn't look stock.
# ---------------------------------------------------------------------------
JAZZMIN_SETTINGS = {
    'site_title': 'SLYK Operator Admin',
    'site_header': 'SLYK',
    'site_brand': 'SLYK Casino',
    'welcome_sign': 'SLYK Casino — Django Admin',
    'copyright': 'SLYK Casino',
    'show_ui_builder': False,
    'navigation_expanded': True,
    'order_with_respect_to': [
        'accounts', 'wallet', 'sportsbook', 'casino', 'promotions', 'livechat', 'notifications',
    ],
    'icons': {
        'auth.user': 'fas fa-user',
        'auth.group': 'fas fa-users',
        'accounts.player': 'fas fa-id-card',
        'accounts.kycsubmission': 'fas fa-file-shield',
        'accounts.auditlog': 'fas fa-list-check',
        'wallet.wallet': 'fas fa-wallet',
        'wallet.ledgerentry': 'fas fa-receipt',
        'sportsbook.event': 'fas fa-futbol',
        'sportsbook.bet': 'fas fa-ticket',
        'promotions.promotion': 'fas fa-gift',
        'promotions.banner': 'fas fa-image',
    },
}

JAZZMIN_UI_TWEAKS = {
    'theme': 'darkly',
    'navbar': 'navbar-dark',
    'navbar_fixed': True,
    'no_navbar_border': True,
    'sidebar': 'sidebar-dark-primary',
    'sidebar_fixed': True,
    'brand_colour': 'navbar-dark',
    'accent': 'accent-warning',
    'button_classes': {
        'primary': 'btn-warning',
        'secondary': 'btn-secondary',
        'info': 'btn-info',
        'warning': 'btn-warning',
        'danger': 'btn-danger',
        'success': 'btn-success',
    },
}
