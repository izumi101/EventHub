"""
Django settings for the EventHub REST API.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'eventhub'),
        'USER': os.environ.get('POSTGRES_USER', 'eventhub_user'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'eventhub_password'),
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
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
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

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')


def _is_placeholder(value):
    return not value or 'your_' in value or value.endswith('_here')


# Simulated payments (tickets confirmed without charging anyone) are an
# explicit local-development opt-in. A missing Stripe key never turns them on.
STRIPE_MOCK_MODE = env_bool('STRIPE_MOCK_MODE', False)
if STRIPE_MOCK_MODE and not DEBUG and not TESTING:
    raise ImproperlyConfigured('STRIPE_MOCK_MODE=1 is only allowed together with DJANGO_DEBUG=1.')

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
    },
}

# ---- Production guard rails: fail at start-up, not at the first sale ---- #
if not DEBUG and not TESTING:
    _problems = []
    if '*' in ALLOWED_HOSTS:
        _problems.append('DJANGO_ALLOWED_HOSTS must list real host names, not "*"')
    if _is_placeholder(STRIPE_SECRET_KEY) or _is_placeholder(STRIPE_WEBHOOK_SECRET):
        _problems.append('STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET must be set')
    if 'console' in EMAIL_BACKEND or 'locmem' in EMAIL_BACKEND:
        _problems.append(
            'EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (or EMAIL_BACKEND) must be set — '
            'sign-up and password-reset codes are delivered by email'
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
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]
