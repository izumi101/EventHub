"""2FA endpoints under /api/v1/auth/mfa/ (docs/adr/0002-two-factor-authentication.md)."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from accounts.schema import AuthPayloadSerializer
from accounts.services import build_auth_payload
from common.schema import ERROR, UNAUTHENTICATED

from . import passkeys, serializers
from .authentication import EnrollmentTokenAuthentication, MFAJWTAuthentication, is_enrollment_auth
from .exceptions import INVALID_TOKEN, MFAError
from .models import EmailCode, EmailFactor, TOTPDevice, WebAuthnCredential
from .policy import METHOD_WEBAUTHN, available_methods, email_allowed_for, mfa_enabled, mfa_required_for
from .services import (
    confirm_totp,
    disable_all,
    enable_email,
    finish_passkey_registration,
    regenerate_recovery_codes,
    remove_email,
    remove_passkey,
    remove_totp,
    rename_passkey,
    send_email_code,
    send_login_email_code,
    start_totp_setup,
    verify_second_factor,
)
from .stepup import require_recent_mfa, step_up_max_age, step_up_valid_until
from .throttling import MFAIPRateThrottle, MFAUserRateThrottle
from .tokens import MFATokenError, issue_jwt_pair, load_challenge, record_challenge_failure, spend, step_up_access_token

MFA_THROTTLES = [*api_settings.DEFAULT_THROTTLE_CLASSES, MFAIPRateThrottle, MFAUserRateThrottle]
WEBAUTHN_OPTIONS = OpenApiResponse(
    OpenApiTypes.OBJECT,
    description='WebAuthn options JSON for navigator.credentials (or @simplewebauthn/browser).',
)
MFA_ERROR = OpenApiResponse(
    ERROR.response,
    description='Refused; `code` is e.g. mfa_invalid, mfa_locked (429, with retry_after), mfa_step_up_required.',
)


def _load_challenge(raw):
    try:
        return load_challenge(raw)
    except MFATokenError as exc:
        raise MFAError(str(exc), INVALID_TOKEN, status_code=status.HTTP_401_UNAUTHORIZED) from exc


def status_payload(request) -> dict:
    user = request.user
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    keys = WebAuthnCredential.objects.filter(user=user)
    email = EmailFactor.objects.filter(user=user).first()
    from .recovery import remaining

    return {
        'enabled': mfa_enabled(user),
        'required': mfa_required_for(user),
        'totp_enabled': device is not None,
        'totp_confirmed_at': device.confirmed_at if device else None,
        'email_enabled': email is not None,
        'email_confirmed_at': email.confirmed_at if email else None,
        'email_allowed': email_allowed_for(user),
        'passkeys': [
            {
                'id': k.pk,
                'name': k.name,
                'created_at': k.created_at,
                'last_used_at': k.last_used_at,
                'backed_up': k.backed_up,
            }
            for k in keys
        ],
        'recovery_codes_remaining': remaining(user),
        'methods': available_methods(user),
        'step_up_max_age': step_up_max_age(),
        'step_up_valid_until': step_up_valid_until(request),
    }


# ---- Login, second step ---- #


class MFALoginVerifyView(APIView):
    """Exchange the login challenge token + one factor for the JWT pair."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = MFA_THROTTLES

    @extend_schema(
        request=serializers.MFALoginVerifyRequestSerializer,
        responses={200: AuthPayloadSerializer, 400: MFA_ERROR, 401: MFA_ERROR, 429: MFA_ERROR},
    )
    def post(self, request):

        data = serializers.MFALoginVerifyRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        token, user = _load_challenge(data.validated_data['challenge_token'])
        method = data.validated_data['method']
        try:
            verify_second_factor(
                user,
                method=method,
                code=data.validated_data.get('code'),
                credential=data.validated_data.get('credential'),
                webauthn_key=passkeys.login_key(token['jti']),
                request=request,
                context='login',
            )
        except MFAError:
            record_challenge_failure(token)
            raise
        if not spend(token):
            raise MFAError(
                'This sign-in step has already been used. Sign in again.',
                INVALID_TOKEN,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(build_auth_payload(user, tokens=issue_jwt_pair(user, method=method)))


class MFALoginWebAuthnOptionsView(APIView):
    """Assertion options for the passkeys of the user behind a challenge token."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = MFA_THROTTLES

    @extend_schema(
        request=serializers.MFAChallengeRequestSerializer,
        responses={200: WEBAUTHN_OPTIONS, 400: ERROR, 401: ERROR},
    )
    def post(self, request):
        data = serializers.MFAChallengeRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        token, user = _load_challenge(data.validated_data['challenge_token'])
        try:
            options = passkeys.authentication_options(user, passkeys.login_key(token['jti']))
        except passkeys.PasskeyError as exc:
            raise MFAError(str(exc), 'mfa_no_passkey') from exc
        return Response(options)


class MFALoginEmailSendView(APIView):
    """Email a sign-in code to the user behind a challenge token."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = MFA_THROTTLES

    @extend_schema(
        request=serializers.MFAChallengeRequestSerializer,
        responses={200: serializers.EmailCodeSentSerializer, 400: ERROR, 401: MFA_ERROR, 429: MFA_ERROR},
        description=(
            'Answers the same whether or not the account has email codes turned on (nothing is sent '
            'then). Limited to one code a minute and five an hour per user (429 `mfa_email_throttled` '
            'with `retry_after`).'
        ),
    )
    def post(self, request):
        data = serializers.MFAChallengeRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _, user = _load_challenge(data.validated_data['challenge_token'])
        return Response(send_login_email_code(user, request=request))


# ---- Status and management ---- #


class MFAStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: serializers.MFAStatusSerializer, 401: UNAUTHENTICATED})
    def get(self, request):
        return Response(status_payload(request))


class _EnrollmentView(APIView):
    """Setup endpoints: a normal access token, or the enrollment token a
    user who must enroll got at login. Adding a factor to an account that
    already has one needs a fresh second factor (step-up)."""

    authentication_classes = [EnrollmentTokenAuthentication, MFAJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def guard_adding_factor(self, request):
        if not is_enrollment_auth(request) and mfa_enabled(request.user):
            require_recent_mfa(request)

    def finish(self, request, result):
        if result.get('tokens') and is_enrollment_auth(request):
            spend(request.auth.token)  # the enrollment token has done its job
        return Response(result)


class TOTPSetupView(_EnrollmentView):
    @extend_schema(
        request=None,
        responses={200: serializers.TOTPSetupResultSerializer, 401: UNAUTHENTICATED, 403: MFA_ERROR, 409: ERROR},
    )
    def post(self, request):
        self.guard_adding_factor(request)
        return Response(start_totp_setup(request.user))


class TOTPConfirmView(_EnrollmentView):
    throttle_classes = MFA_THROTTLES

    @extend_schema(
        request=serializers.CodeRequestSerializer,
        responses={200: serializers.FactorAddedSerializer, 400: MFA_ERROR, 401: UNAUTHENTICATED, 409: ERROR},
    )
    def post(self, request):
        data = serializers.CodeRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.finish(request, confirm_totp(request.user, data.validated_data['code'], request=request))


class TOTPDeviceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: serializers.MFAStatusSerializer, 401: UNAUTHENTICATED, 403: MFA_ERROR, 409: ERROR})
    def delete(self, request):
        require_recent_mfa(request)
        remove_totp(request.user, request=request)
        return Response(status_payload(request))


class PasskeyRegisterOptionsView(_EnrollmentView):
    @extend_schema(
        request=serializers.PasskeyOptionsRequestSerializer,
        responses={200: WEBAUTHN_OPTIONS, 400: ERROR, 401: UNAUTHENTICATED, 403: MFA_ERROR},
    )
    def post(self, request):
        self.guard_adding_factor(request)
        data = serializers.PasskeyOptionsRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            return Response(passkeys.registration_options(request.user, data.validated_data.get('name') or ''))
        except passkeys.PasskeyError as exc:
            raise MFAError(str(exc), 'mfa_passkey_limit') from exc


class PasskeyRegisterVerifyView(_EnrollmentView):
    @extend_schema(
        request=serializers.PasskeyRegisterRequestSerializer,
        responses={200: serializers.FactorAddedSerializer, 400: MFA_ERROR, 401: UNAUTHENTICATED},
    )
    def post(self, request):
        data = serializers.PasskeyRegisterRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = finish_passkey_registration(
            request.user, data.validated_data['credential'], data.validated_data.get('name'), request=request
        )
        return self.finish(request, result)


class EmailSendView(_EnrollmentView):
    """Email a code to turn on email codes (enrollment) or for step-up."""

    throttle_classes = MFA_THROTTLES

    @extend_schema(
        request=serializers.EmailSendRequestSerializer,
        responses={
            200: serializers.EmailCodeSentSerializer,
            400: MFA_ERROR,
            401: UNAUTHENTICATED,
            403: MFA_ERROR,
            409: ERROR,
            429: MFA_ERROR,
        },
    )
    def post(self, request):
        data = serializers.EmailSendRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        purpose = data.validated_data['purpose']
        if purpose == EmailCode.PURPOSE_ENROLL:
            self.guard_adding_factor(request)
        elif is_enrollment_auth(request):
            raise MFAError('Set up a second factor first.', 'mfa_not_enabled')
        return Response(send_email_code(request.user, purpose, request=request))


class EmailEnableView(_EnrollmentView):
    throttle_classes = MFA_THROTTLES

    @extend_schema(
        request=serializers.CodeRequestSerializer,
        responses={
            200: serializers.FactorAddedSerializer,
            400: MFA_ERROR,
            401: UNAUTHENTICATED,
            403: MFA_ERROR,
            409: ERROR,
        },
    )
    def post(self, request):
        self.guard_adding_factor(request)
        data = serializers.CodeRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self.finish(request, enable_email(request.user, data.validated_data['code'], request=request))


class EmailDisableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: serializers.MFAStatusSerializer, 401: UNAUTHENTICATED, 403: MFA_ERROR, 404: ERROR, 409: ERROR},
    )
    def post(self, request):
        require_recent_mfa(request)
        remove_email(request.user, request=request)
        return Response(status_payload(request))


class PasskeyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=serializers.PasskeyRenameRequestSerializer,
        responses={200: serializers.MFAStatusSerializer, 400: ERROR, 401: UNAUTHENTICATED, 404: ERROR},
    )
    def patch(self, request, pk):
        data = serializers.PasskeyRenameRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        rename_passkey(request.user, pk, data.validated_data['name'])
        return Response(status_payload(request))

    @extend_schema(
        responses={200: serializers.MFAStatusSerializer, 401: UNAUTHENTICATED, 403: MFA_ERROR, 404: ERROR, 409: ERROR}
    )
    def delete(self, request, pk):
        require_recent_mfa(request)
        remove_passkey(request.user, pk, request=request)
        return Response(status_payload(request))


class RecoveryCodesRegenerateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: serializers.RecoveryCodesSerializer, 400: ERROR, 401: UNAUTHENTICATED, 403: MFA_ERROR},
    )
    def post(self, request):
        require_recent_mfa(request)
        return Response({'recovery_codes': regenerate_recovery_codes(request.user, request=request)})


class MFADisableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None, responses={200: serializers.MFAStatusSerializer, 401: UNAUTHENTICATED, 403: MFA_ERROR, 409: ERROR}
    )
    def post(self, request):
        require_recent_mfa(request)
        disable_all(request.user, request=request)
        return Response(status_payload(request))


# ---- Step-up ---- #


class StepUpWebAuthnOptionsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = MFA_THROTTLES

    @extend_schema(request=None, responses={200: WEBAUTHN_OPTIONS, 400: ERROR, 401: UNAUTHENTICATED})
    def post(self, request):
        try:
            return Response(passkeys.authentication_options(request.user, passkeys.step_up_key(request.user)))
        except passkeys.PasskeyError as exc:
            raise MFAError(str(exc), 'mfa_no_passkey') from exc


class StepUpView(APIView):
    """Prove a second factor again; returns an access token with a new mfa_at."""

    permission_classes = [IsAuthenticated]
    throttle_classes = MFA_THROTTLES

    @extend_schema(
        request=serializers.StepUpRequestSerializer,
        responses={200: serializers.StepUpResultSerializer, 400: MFA_ERROR, 401: UNAUTHENTICATED, 429: MFA_ERROR},
    )
    def post(self, request):
        data = serializers.StepUpRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        method = data.validated_data['method']
        verify_second_factor(
            request.user,
            method=method,
            code=data.validated_data.get('code'),
            credential=data.validated_data.get('credential'),
            webauthn_key=passkeys.step_up_key(request.user) if method == METHOD_WEBAUTHN else None,
            request=request,
            context='step_up',
        )
        access, mfa_at = step_up_access_token(request.user, request.auth, method)
        return Response({'access': access, 'mfa_at': mfa_at, 'valid_until': mfa_at + step_up_max_age()})
