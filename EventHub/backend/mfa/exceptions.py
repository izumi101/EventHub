"""API errors with stable `code`s the SPA branches on."""

from rest_framework import status
from rest_framework.exceptions import APIException, AuthenticationFailed

STEP_UP_REQUIRED = 'mfa_step_up_required'
ENROLLMENT_REQUIRED = 'mfa_enrollment_required'
MFA_REQUIRED = 'mfa_required'
LOCKED = 'mfa_locked'
INVALID_CODE = 'mfa_invalid'
INVALID_TOKEN = 'mfa_token_invalid'  # noqa: S105 - an error code, not a secret
REQUIRED_BY_POLICY = 'mfa_required_by_policy'


class MFAError(APIException):
    """Rendered by common.exceptions.exception_handler as
    {"error": message, "code": code, **extra}."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Two-factor authentication failed.'
    default_code = INVALID_CODE

    def __init__(self, detail=None, code=None, *, extra=None, status_code=None):
        super().__init__(detail=detail or self.default_detail, code=code or self.default_code)
        self.mfa_code = code or self.default_code
        self.extra = extra or {}
        if status_code is not None:
            self.status_code = status_code


class StepUpRequired(MFAError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Confirm it is you with your second factor to continue.'
    default_code = STEP_UP_REQUIRED


class EnrollmentRequired(MFAError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Set up two-factor authentication (Profile → Security) to do this.'
    default_code = ENROLLMENT_REQUIRED


class MFALocked(MFAError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = 'Too many wrong codes. Try again later.'
    default_code = LOCKED


class TokenWithoutMFA(AuthenticationFailed):
    """An access token that does not record a second factor, for a user who
    needs one (401 — the SPA signs in again)."""

    default_detail = 'Sign in again with your second factor.'
    default_code = MFA_REQUIRED
