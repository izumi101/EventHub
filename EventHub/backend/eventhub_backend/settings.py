"""
Django settings for the EventHub REST API.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from mfa.conf import DEV_ENCRYPTION_KEY as _default_mfa_key
from mfa.conf import production_problems as mfa_production_problems
from payments.providers.conf import parse_enabled as parse_enabled_providers
from payments.providers.conf import production_problems as payment_production_problems
from payments.providers.conf import unknown_codes as unknown_payment_providers

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# `manage.py test` runs with DEBUG off but must not need production secrets.
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(',') if item.strip()]


_default_key = 'django-insecure-dev-only-change-me'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', _default_key)
DEBUG = env_bool('DJANGO_DEBUG', False)

if not DEBUG and not TESTING and _default_key == SECRET_KEY:
    raise RuntimeError(
        'You must set DJANGO_SECRET_KEY environment variable in production! '
        'Generate one with: python -c '
        '"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )
ALLOWED_HOSTS = env_list(
    'DJANGO_ALLOWED_HOSTS',
    ['localhost', '127.0.0.1', 'backend'] if not DEBUG else ['*'],
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'corsheaders',
    'channels',
    'django.contrib.postgres',
    'accounts',
    'events',
    'payments',
    'bookings',
    'jobs',
    'featureflags',
    'mfa',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'common.api_versioning.DeprecatedApiMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Staff sessions in /admin/ must pass a second factor (docs/SECURITY_2FA.md).
    'mfa.middleware.AdminMFAMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'eventhub_backend.urls'

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

WSGI_APPLICATION = 'eventhub_backend.wsgi.application'
ASGI_APPLICATION = 'eventhub_backend.asgi.application'

# Django Channels — Redis channel layer for real-time WebSocket pub/sub
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [REDIS_URL],
            'capacity': 1500,
            'expiry': 10,
        },
    },
}

# Shared cache: throttling counters must be shared by every worker process
# (a per-process LocMem cache multiplies every rate limit by the worker count).
CACHES = {
    'default': (
        {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': REDIS_URL}
        if os.environ.get('REDIS_URL') and not TESTING
        else {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
    ),
}

# ---- Database roles (docs/DATABASE_ROLES.md) ---- #
# POSTGRES_USER owns the schema: it runs the migrations and creates the roles
# below (`manage.py setup_db_roles`, run by entrypoint.sh after `migrate`).
# Everything else (gunicorn, the worker, ordinary manage.py commands) connects
# as the least-privilege POSTGRES_APP_USER (data only, no DDL) once
# POSTGRES_APP_PASSWORD is set. Without it (an .env from before the roles
# existed) the app keeps connecting as the owner and prints a warning.
# The owner is always used by the test runner (it needs CREATEDB), by the
# commands in DB_OWNER_COMMANDS and by a process started with
# DJANGO_DB_AS_OWNER=1.
DB_OWNER_USER = os.environ.get('POSTGRES_USER', 'eventhub_user')
DB_OWNER_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'eventhub_password')
DB_APP_USER = os.environ.get('POSTGRES_APP_USER', '').strip() or 'eventhub_app'
DB_APP_PASSWORD = os.environ.get('POSTGRES_APP_PASSWORD', '')
DB_READONLY_USER = os.environ.get('POSTGRES_READONLY_USER', '').strip() or 'eventhub_readonly'
DB_READONLY_PASSWORD = os.environ.get('POSTGRES_READONLY_PASSWORD', '')
DB_OWNER_COMMANDS = {'migrate', 'setup_db_roles', 'verify_db_roles'}
DB_AS_OWNER = (
    TESTING
    or env_bool('DJANGO_DB_AS_OWNER', False)
    or (len(sys.argv) > 1 and Path(sys.argv[0]).name == 'manage.py' and sys.argv[1] in DB_OWNER_COMMANDS)
)
DB_USES_APP_ROLE = bool(DB_APP_PASSWORD) and not DB_AS_OWNER
if not DB_APP_PASSWORD and not DB_AS_OWNER:
    sys.stderr.write(
        f'WARNING: POSTGRES_APP_PASSWORD is not set, so the app connects to PostgreSQL as the schema owner '
        f'"{DB_OWNER_USER}". Set POSTGRES_APP_PASSWORD (and POSTGRES_READONLY_PASSWORD) to use the '
        f'least-privilege roles (docs/DATABASE_ROLES.md).\n'
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'eventhub'),
        'USER': DB_APP_USER if DB_USES_APP_ROLE else DB_OWNER_USER,
        'PASSWORD': DB_APP_PASSWORD if DB_USES_APP_ROLE else DB_OWNER_PASSWORD,
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': int(os.environ.get('POSTGRES_CONN_MAX_AGE', '60')),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.environ.get('DJANGO_TIME_ZONE', 'UTC')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    # SimpleJWT access tokens plus the 2FA policy (mfa/authentication.py).
    'DEFAULT_AUTHENTICATION_CLASSES': ('mfa.authentication.MFAJWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticatedOrReadOnly',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 12,
    'EXCEPTION_HANDLER': 'common.exceptions.exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'common.openapi.AutoSchema',
    # Only nginx talks to Django; it appends the real client address as the
    # last X-Forwarded-For entry. Without this DRF would trust the whole,
    # client-supplied header and every request could fake a new identity.
    'NUM_PROXIES': int(os.environ.get('DJANGO_NUM_PROXIES', '1')),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '300/min',
        'user': '1200/min',
        'login': '5/min',
        'register': '3/min',
        'password_reset': '3/min',
        'change_password': '5/min',
        'token_refresh': '30/min',
        'promo': '10/min',
        'claim': '10/min',
        'affiliate_click': '30/min',
    },
}

# ---- API contract ---- #
# /api/v1/ is canonical; the unversioned /api/ alias answers with Deprecation
# and Sunset headers until it is removed (common/api_versioning.py).
API_LEGACY_DEPRECATED_ON = '2026-10-30'
API_LEGACY_SUNSET_ON = '2027-04-30'

SPECTACULAR_SETTINGS = {
    'TITLE': 'EventHub API',
    'DESCRIPTION': (
        'Events, tickets, seat maps, payments and check-in. Authenticate with '
        '`Authorization: Bearer <access token>` from `POST /api/v1/auth/login/`. '
        'Errors are `{"error": "<message>"}`, with a stable `code` where clients '
        'branch on it.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Swagger UI from our own static files: the CSP allows no CDNs.
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    # Separate request/response components, so generated clients don't make
    # read-only fields required on input.
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/v1',
    'PREPROCESSING_HOOKS': ['common.openapi.only_current_version'],
    # Stable, readable names for value sets that share a field name
    # (`status`, `type`, ...) — generated clients use them as type names.
    'ENUM_NAME_OVERRIDES': {
        'EventStatusEnum': 'common.choices.EventStatusChoices',
        'RegistrationStatusEnum': 'common.choices.RegistrationStatusChoices',
        'PaymentStatusEnum': 'common.choices.PaymentStatusChoices',
        'PaymentMethodEnum': 'payments.models.Payment.METHOD_CHOICES',
        'BookingStatusEnum': 'bookings.models.Booking.Status',
        'RefundRequestStatusEnum': 'events.models.RefundRequest.STATUS_CHOICES',
        'WaitlistEntryStatusEnum': 'events.models.WaitlistEntry.STATUS_CHOICES',
        'WaitlistStatusEnum': 'events.schema.WAITLIST_STATUSES',
        'QueueStatusEnum': 'events.schema.QUEUE_STATUSES',
        'DemandLevelEnum': 'events.schema.DEMAND_LEVELS',
        'TicketScanResultEnum': 'events.schema.SCAN_RESULTS',
        'TicketScanRefusalEnum': 'events.schema.SCAN_REFUSALS',
        'QuestionTypeEnum': 'events.models.EventQuestion.TYPE_CHOICES',
        'PriceZoneEnum': 'events.models.EventSeat.PRICE_ZONE_CHOICES',
        'NotificationTypeEnum': 'events.models.Notification.TYPE_CHOICES',
        'TicketKindEnum': 'events.models.TicketType.KIND_CHOICES',
        'CheckInActionEnum': 'events.models.CheckInLog.ACTION_CHOICES',
        'WebhookTriggerEnum': 'events.models.Webhook.TRIGGER_CHOICES',
        'MFAMethodEnum': 'mfa.serializers.METHOD_CHOICES',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

CORS_ALLOWED_ORIGINS = env_list(
    'DJANGO_CORS_ALLOWED_ORIGINS',
    ['http://localhost:4200', 'http://127.0.0.1:4200'],
)
CORS_ALLOW_ALL_ORIGINS = env_bool('DJANGO_CORS_ALLOW_ALL_ORIGINS', DEBUG)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    ['http://localhost:4200', 'http://127.0.0.1:4200'],
)

SESSION_COOKIE_SECURE = env_bool('DJANGO_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('DJANGO_CSRF_COOKIE_SECURE', not DEBUG)
SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:4200').rstrip('/')

# ---- Two-factor authentication (docs/adr/0002-two-factor-authentication.md) ---- #
# Roles that must use 2FA: organizer, staff (is_staff), superuser, attendee.
# Empty turns enforcement off (staged rollout); users who enrolled keep
# being asked for their factor either way.
MFA_REQUIRED_ROLES = env_list('MFA_REQUIRED_ROLES', ['organizer', 'staff', 'superuser'])
if _unknown_mfa_roles := sorted(set(MFA_REQUIRED_ROLES) - {'attendee', 'organizer', 'staff', 'superuser'}):
    raise ImproperlyConfigured(
        f'MFA_REQUIRED_ROLES lists unknown roles: {", ".join(_unknown_mfa_roles)} '
        '(allowed: attendee, organizer, staff, superuser)'
    )
# Key(s) for encrypting TOTP secrets at rest; comma separated for rotation
# (the first encrypts, all decrypt). Required when DJANGO_DEBUG=0.
MFA_ENCRYPTION_KEYS = env_list('MFA_ENCRYPTION_KEY', []) or [_default_mfa_key]
# How long a second-factor proof covers sensitive actions (step-up).
MFA_STEP_UP_MAX_AGE_SECONDS = int(os.environ.get('MFA_STEP_UP_MAX_AGE_SECONDS', '600'))
MFA_CHALLENGE_TTL_SECONDS = 300
MFA_ENROLLMENT_TTL_SECONDS = 900
MFA_WEBAUTHN_CHALLENGE_TTL_SECONDS = 300
MFA_TOTP_ISSUER = os.environ.get('MFA_TOTP_ISSUER', 'EventHub')
# Lockout: after MFA_MAX_FAILED_ATTEMPTS consecutive wrong codes the user is
# locked for MFA_LOCKOUT_SECONDS, doubling per further failure up to the max.
MFA_MAX_FAILED_ATTEMPTS = 5
MFA_LOCKOUT_SECONDS = 60
MFA_LOCKOUT_MAX_SECONDS = 3600
# DRF throttles of the second-factor endpoints (per client IP / per user).
MFA_THROTTLE_RATES = {'mfa_ip': '20/min', 'mfa_user': '10/min'}
# Email codes as a second factor (ADR 0002, amendment 1). Weaker than TOTP or
# passkeys (a taken-over mailbox gets both the password reset and the code):
# set MFA_EMAIL_ALLOWED_FOR_REQUIRED_ROLES=0 to make organizers/staff use an
# authenticator app or a passkey instead.
MFA_EMAIL_ALLOWED_FOR_REQUIRED_ROLES = env_bool('MFA_EMAIL_ALLOWED_FOR_REQUIRED_ROLES', True)
MFA_EMAIL_CODE_TTL_SECONDS = 600
MFA_EMAIL_CODE_MAX_ATTEMPTS = 5
# Sending limits per user and purpose (sign-in, step-up, enrollment): one code
# a minute, five an hour.
MFA_EMAIL_RESEND_SECONDS = 60
MFA_EMAIL_MAX_PER_HOUR = 5
# WebAuthn: the RP ID is the site's host name (no scheme or port) and every
# origin the SPA is opened from must be listed. Passkeys need a secure
# context: https, or http://localhost; a plain-HTTP LAN IP can't use them.
WEBAUTHN_RP_ID = os.environ.get('WEBAUTHN_RP_ID', 'localhost').strip()
WEBAUTHN_RP_NAME = os.environ.get('WEBAUTHN_RP_NAME', 'EventHub')
WEBAUTHN_ORIGINS = env_list('WEBAUTHN_ORIGINS', ['http://localhost:4200', 'https://localhost'])

# ---- Payments (docs/adr/0001-payment-provider-layer.md) ---- #
# Providers that may take money, comma separated. Each enabled provider must
# be fully configured when DJANGO_DEBUG=0 (see the guard at the bottom).
PAYMENT_PROVIDERS_ENABLED = parse_enabled_providers(os.environ.get('PAYMENT_PROVIDERS_ENABLED', 'stripe'))

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
# Only for pointing the Stripe provider at a local fake (e.g. stripe-mock);
# empty means Stripe's own API address.
STRIPE_API_BASE = os.environ.get('STRIPE_API_BASE', '').strip()

# Freedom Pay (KZT, docs/payments/freedompay-protocol.md). No default API
# address: the demo points it at the emulator (http://fpay-emulator:8080).
# FREEDOMPAY_RESULT_URL is the callback address the gateway can reach,
# e.g. https://eventhub.example/api/v1/payments/callback/freedompay/.
FREEDOMPAY_API_URL = os.environ.get('FREEDOMPAY_API_URL', '').strip().rstrip('/')
FREEDOMPAY_MERCHANT_ID = os.environ.get('FREEDOMPAY_MERCHANT_ID', '').strip()
FREEDOMPAY_SECRET_KEY = os.environ.get('FREEDOMPAY_SECRET_KEY', '')
FREEDOMPAY_RESULT_URL = os.environ.get('FREEDOMPAY_RESULT_URL', '').strip()
# pg_testing_mode=1 on every payment (test transactions only).
FREEDOMPAY_TESTING_MODE = env_bool('FREEDOMPAY_TESTING_MODE', False)
# Lets a DJANGO_DEBUG=0 deployment use the emulator and demo keys (a demo
# that never takes real money); the start-up guard refuses them otherwise.
FREEDOMPAY_DEMO_MODE = env_bool('FREEDOMPAY_DEMO_MODE', False)

# Simulated payments (tickets confirmed without charging anyone) are an
# explicit local-development opt-in. A missing provider key never turns them
# on. STRIPE_MOCK_MODE is the deprecated name, used while PAYMENTS_MOCK_MODE
# is unset or empty; the legacy services still read the STRIPE_MOCK_MODE
# setting, which always mirrors PAYMENTS_MOCK_MODE.
PAYMENTS_MOCK_MODE = (
    env_bool('PAYMENTS_MOCK_MODE', False)
    if os.environ.get('PAYMENTS_MOCK_MODE', '').strip()
    else env_bool('STRIPE_MOCK_MODE', False)
)
STRIPE_MOCK_MODE = PAYMENTS_MOCK_MODE
if PAYMENTS_MOCK_MODE and not DEBUG and not TESTING:
    raise ImproperlyConfigured(
        'PAYMENTS_MOCK_MODE=1 (or the deprecated STRIPE_MOCK_MODE=1) is only allowed together with DJANGO_DEBUG=1.'
    )
if _unknown_providers := unknown_payment_providers(PAYMENT_PROVIDERS_ENABLED):
    raise ImproperlyConfigured(
        f'PAYMENT_PROVIDERS_ENABLED lists unknown payment providers: {", ".join(_unknown_providers)}'
    )

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)

EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')

# Without SMTP credentials the smtp backend would raise on every send and
# block flows that depend on email (registration codes, password reset).
# Fall back to the console backend so codes land in the server log instead.
_default_email_backend = (
    'django.core.mail.backends.smtp.EmailBackend'
    if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
    else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', _default_email_backend)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'EventHub <no-reply@eventhub.local>')

# Background jobs (emails, webhooks, search indexing) are executed by
# `manage.py run_worker`. JOBS_RUN_INLINE=1 runs them right after the request's
# transaction commits instead — handy for local development without a worker.
JOBS_RUN_INLINE = env_bool('JOBS_RUN_INLINE', False)

# ---- Feature flags (self-hosted Unleash; featureflags app) ---- #
# Off by default and always off in tests: every flag then answers with its
# default from featureflags/registry.py. The client is created lazily in each
# worker process and polls in the background, so Unleash being slow or down
# never blocks or fails a request (docs/FEATURE_FLAGS.md).
UNLEASH_ENABLED = env_bool('UNLEASH_ENABLED', False) and not TESTING
# The client API base, e.g. http://unleash:4242/api
UNLEASH_URL = os.environ.get('UNLEASH_URL', '').strip()
# A backend token ("<project>:<environment>.<secret>"); its environment decides
# which flag configuration this deployment gets. Never sent to the browser.
UNLEASH_API_TOKEN = os.environ.get('UNLEASH_API_TOKEN', '').strip()
UNLEASH_APP_NAME = os.environ.get('UNLEASH_APP_NAME', 'eventhub-backend')
UNLEASH_ENVIRONMENT = os.environ.get('UNLEASH_ENVIRONMENT', 'development' if DEBUG else 'production')
UNLEASH_REFRESH_INTERVAL = int(os.environ.get('UNLEASH_REFRESH_INTERVAL', '15'))
UNLEASH_METRICS_INTERVAL = int(os.environ.get('UNLEASH_METRICS_INTERVAL', '60'))
UNLEASH_REQUEST_TIMEOUT = int(os.environ.get('UNLEASH_REQUEST_TIMEOUT', '5'))
if UNLEASH_ENABLED and not (UNLEASH_URL and UNLEASH_API_TOKEN):
    raise ImproperlyConfigured(
        'UNLEASH_ENABLED=1 needs UNLEASH_URL and UNLEASH_API_TOKEN (see .env.example); '
        'set UNLEASH_ENABLED=0 to run with the flag defaults.'
    )

# ---- Logging ---- #
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'filters': {
        # One copy of each Unleash SDK message per 5 minutes per process: an
        # outage would otherwise log a traceback on every poll.
        'unleash_rate_limit': {
            '()': 'featureflags.log_filters.RateLimitFilter',
            'interval': 300,
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'accounts': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'events': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'payments': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'bookings': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'jobs': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'featureflags': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # 2FA audit trail: enable/disable, failures, lockouts, resets (no secrets).
        'mfa': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # The Unleash SDK and its scheduler log every poll at INFO.
        'UnleashClient': {
            'handlers': ['console'],
            'level': 'WARNING',
            'filters': ['unleash_rate_limit'],
            'propagate': False,
        },
        'apscheduler': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ---- Production guard rails: fail at start-up, not at the first sale ---- #
if not DEBUG and not TESTING:
    _problems = []
    if '*' in ALLOWED_HOSTS:
        _problems.append('DJANGO_ALLOWED_HOSTS must list real host names, not "*"')
    _problems += payment_production_problems(
        PAYMENT_PROVIDERS_ENABLED, mock_mode=PAYMENTS_MOCK_MODE, get_setting=lambda name: globals().get(name)
    )
    if 'console' in EMAIL_BACKEND or 'locmem' in EMAIL_BACKEND:
        _problems.append(
            'EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (or EMAIL_BACKEND) must be set — '
            'sign-up and password-reset codes are delivered by email'
        )
    if DB_APP_PASSWORD and DB_APP_USER in (DB_OWNER_USER, DB_READONLY_USER):
        _problems.append(
            'POSTGRES_APP_USER must be its own role, not POSTGRES_USER or POSTGRES_READONLY_USER '
            '(docs/DATABASE_ROLES.md)'
        )
    _problems += mfa_production_problems(
        encryption_keys=env_list('MFA_ENCRYPTION_KEY', []), rp_id=WEBAUTHN_RP_ID, origins=WEBAUTHN_ORIGINS
    )
    if _problems:
        raise ImproperlyConfigured(
            'Refusing to start with DJANGO_DEBUG=0: '
            + '; '.join(_problems)
            + '. For local development set DJANGO_DEBUG=1 (see .env.example).'
        )

if TESTING:
    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {}
    # Tests share one client IP; throttling tests turn these on explicitly.
    MFA_THROTTLE_RATES = {}
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]
