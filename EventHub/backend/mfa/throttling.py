"""Throttles for second-factor attempts, per client IP and per user.

Rates come from settings.MFA_THROTTLE_RATES (read per request, so tests can
override them); a missing rate disables that throttle. These sit on top of
the per-user lockout in mfa/services.py.
"""

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class _MFARateThrottle(SimpleRateThrottle):
    scope = ''

    def __init__(self):
        # SimpleRateThrottle reads THROTTLE_RATES at construction; ours live
        # in Django settings.
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate) if self.rate else (None, None)

    def get_rate(self):
        return (getattr(settings, 'MFA_THROTTLE_RATES', None) or {}).get(self.scope)

    def allow_request(self, request, view):
        if self.rate is None:
            return True
        return super().allow_request(request, view)


class MFAIPRateThrottle(_MFARateThrottle):
    scope = 'mfa_ip'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class MFAUserRateThrottle(_MFARateThrottle):
    """Keyed on the user the attempt is for: the signed-in user, or the user
    named by the challenge token (checked without consuming it)."""

    scope = 'mfa_user'

    def get_cache_key(self, request, view):
        user_id = None
        if request.user and request.user.is_authenticated:
            user_id = request.user.pk
        else:
            from rest_framework_simplejwt.settings import api_settings as jwt_settings

            from .tokens import MFAChallengeToken

            raw = request.data.get('challenge_token') if hasattr(request, 'data') else None
            if isinstance(raw, str) and raw:
                try:
                    user_id = MFAChallengeToken(raw).get(jwt_settings.USER_ID_CLAIM)
                except Exception:
                    user_id = None
        if user_id is None:
            return None  # nothing to key on; the IP throttle still applies
        return self.cache_format % {'scope': self.scope, 'ident': user_id}
