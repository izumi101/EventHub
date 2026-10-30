"""API versioning: /api/v1/ is canonical, unversioned /api/ is a deprecated alias.

Responses served through the alias carry `Deprecation` (RFC 9745), `Sunset`
(RFC 8594) and a `Link` to the /api/v1/ successor, so clients learn about the
move from every response. Paths that third parties call at a fixed address
(payment provider callbacks) and infrastructure probes stay unversioned and
are never marked deprecated.
"""

from datetime import datetime, timezone

from django.conf import settings
from django.utils.http import http_date

CURRENT_PREFIX = '/api/v1/'
LEGACY_PREFIX = '/api/'

# Fixed addresses registered with external systems (payment dashboards,
# load balancers); they keep working without a version.
STABLE_PATHS = (
    '/api/health/',
    '/api/payments/webhook/',
)


def _timestamp(iso_date: str) -> int:
    return int(datetime.fromisoformat(iso_date).replace(tzinfo=timezone.utc).timestamp())


def is_legacy_api_path(path: str) -> bool:
    return path.startswith(LEGACY_PREFIX) and not path.startswith(CURRENT_PREFIX) and not path.startswith(STABLE_PATHS)


class DeprecatedApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.deprecation = f'@{_timestamp(settings.API_LEGACY_DEPRECATED_ON)}'
        self.sunset = http_date(_timestamp(settings.API_LEGACY_SUNSET_ON))

    def __call__(self, request):
        response = self.get_response(request)
        if is_legacy_api_path(request.path):
            successor = CURRENT_PREFIX + request.path[len(LEGACY_PREFIX) :]
            response['Deprecation'] = self.deprecation
            response['Sunset'] = self.sunset
            response['Link'] = f'<{successor}>; rel="successor-version"'
        return response
