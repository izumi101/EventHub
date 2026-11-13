"""DRF authentication classes.

MFAJWTAuthentication replaces SimpleJWT's JWTAuthentication for the whole
API: same access tokens, plus the 2FA policy — a user who must have (or has
enabled) 2FA is refused a token that does not record a second factor.

EnrollmentTokenAuthentication accepts the enrollment-scoped token issued at
login to a user who must enroll; it is only listed on the enrollment views.
"""

from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from .exceptions import TokenWithoutMFA
from .policy import mfa_enabled, token_satisfies_policy
from .tokens import MFAEnrollmentToken, MFATokenError, load_enrollment


class MFAJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        # The 2FA policy looks at the profile role on every request: load it
        # in the same query.
        try:
            user_id = validated_token[jwt_settings.USER_ID_CLAIM]
        except KeyError:
            return super().get_user(validated_token)
        user = User.objects.select_related('profile').filter(**{jwt_settings.USER_ID_FIELD: user_id}).first()
        if user is None or not user.is_active:
            return super().get_user(validated_token)  # raises the usual errors
        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        if not token_satisfies_policy(user, token):
            raise TokenWithoutMFA()
        return user, token


class EnrollmentToken:
    """request.auth for a request authenticated by an enrollment token."""

    is_enrollment = True

    def __init__(self, token):
        self.token = token

    def get(self, key, default=None):
        return self.token.get(key, default)


class EnrollmentTokenAuthentication(BaseAuthentication):
    """`Authorization: Bearer <enrollment token>`. Returns None for any other
    token so the next class (MFAJWTAuthentication) can try it."""

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if len(header) != 2 or header[0].lower() != b'bearer':
            return None
        raw = header[1].decode(errors='ignore')
        try:
            MFAEnrollmentToken(raw)
        except Exception:
            return None  # not an enrollment token (or a broken one): let JWT auth decide
        try:
            token, user = load_enrollment(raw)
        except MFATokenError as exc:
            raise AuthenticationFailed(str(exc), code='mfa_token_invalid') from exc
        if mfa_enabled(user):
            # Someone already enrolled: the token can't add more factors.
            raise AuthenticationFailed('Two-factor authentication is already set up. Sign in again.')
        return user, EnrollmentToken(token)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


def is_enrollment_auth(request) -> bool:
    return getattr(request.auth, 'is_enrollment', False)
