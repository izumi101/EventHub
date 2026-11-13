"""OpenAPI descriptions of the 2FA authentication classes (drf-spectacular
extensions, registered on import from MfaConfig.ready)."""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class MFAJWTScheme(SimpleJWTScheme):
    """Same bearer access token as before (`jwtAuth`), plus the 2FA policy."""

    target_class = 'mfa.authentication.MFAJWTAuthentication'
    name = 'jwtAuth'


class EnrollmentTokenScheme(OpenApiAuthenticationExtension):
    target_class = 'mfa.authentication.EnrollmentTokenAuthentication'
    name = 'mfaEnrollmentToken'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': (
                'The `enrollment_token` from POST /auth/login/ (`mfa_enrollment_required`): '
                'accepted by the 2FA setup endpoints only.'
            ),
        }
