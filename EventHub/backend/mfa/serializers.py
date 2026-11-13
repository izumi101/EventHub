"""Request/response shapes of the 2FA endpoints (validation + OpenAPI)."""

from rest_framework import serializers

from accounts.schema import TokenPairSerializer
from accounts.serializers import UserSerializer

from .policy import METHOD_RECOVERY, METHOD_TOTP, METHOD_WEBAUTHN

METHOD_CHOICES = [
    (METHOD_TOTP, 'Authenticator app code'),
    (METHOD_WEBAUTHN, 'Passkey / security key'),
    (METHOD_RECOVERY, 'Recovery code'),
]


class _FactorProofSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=METHOD_CHOICES)
    code = serializers.CharField(
        required=False, allow_blank=True, max_length=64, help_text='TOTP code or recovery code.'
    )
    credential = serializers.DictField(
        required=False, help_text='WebAuthn assertion (PublicKeyCredential JSON) for method=webauthn.'
    )

    def validate(self, attrs):
        if attrs['method'] == METHOD_WEBAUTHN:
            if not attrs.get('credential'):
                raise serializers.ValidationError({'credential': 'The passkey response is required.'})
        elif not (attrs.get('code') or '').strip():
            raise serializers.ValidationError({'code': 'Enter the code.'})
        return attrs


class MFALoginVerifyRequestSerializer(_FactorProofSerializer):
    challenge_token = serializers.CharField()


class MFAChallengeRequestSerializer(serializers.Serializer):
    challenge_token = serializers.CharField()


class StepUpRequestSerializer(_FactorProofSerializer):
    pass


class StepUpResultSerializer(serializers.Serializer):
    access = serializers.CharField(help_text='New access token; send it from now on.')
    mfa_at = serializers.IntegerField(help_text='Unix time of this proof.')
    valid_until = serializers.IntegerField(help_text='Unix time until which sensitive actions need no new proof.')


class TOTPSetupResultSerializer(serializers.Serializer):
    secret = serializers.CharField(help_text='Base32 secret for manual entry; shown during setup only.')
    otpauth_uri = serializers.CharField(help_text='otpauth:// URI for the QR code.')


class CodeRequestSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=16)


class PasskeyOptionsRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=64)


class PasskeyRegisterRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=64)
    credential = serializers.DictField(help_text='Attestation (PublicKeyCredential JSON).')


class FactorAddedSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    recovery_codes = serializers.ListField(
        child=serializers.CharField(),
        allow_null=True,
        help_text='Only when this was the first factor: shown once, store them safely.',
    )
    tokens = TokenPairSerializer(
        allow_null=True, help_text='Only for the first factor: a new pair (other sessions are signed out).'
    )
    user = UserSerializer(allow_null=True)


class RecoveryCodesSerializer(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField())


class PasskeySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField(allow_null=True)
    backed_up = serializers.BooleanField(help_text='Synced passkey (e.g. iCloud Keychain, Google Password Manager).')


class MFAStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    required = serializers.BooleanField(help_text='Your role must use two-factor authentication.')
    totp_enabled = serializers.BooleanField()
    totp_confirmed_at = serializers.DateTimeField(allow_null=True)
    passkeys = PasskeySerializer(many=True)
    recovery_codes_remaining = serializers.IntegerField()
    methods = serializers.ListField(child=serializers.CharField())
    step_up_max_age = serializers.IntegerField(help_text='Seconds a second-factor proof covers sensitive actions.')
    step_up_valid_until = serializers.IntegerField(
        allow_null=True, help_text='Unix time until which the current token covers sensitive actions.'
    )


class MFAChallengeSerializer(serializers.Serializer):
    mfa_required = serializers.BooleanField()
    challenge_token = serializers.CharField(help_text='Single-purpose, short-lived; not an access token.')
    methods = serializers.ListField(child=serializers.ChoiceField(choices=METHOD_CHOICES))
    expires_in = serializers.IntegerField()


class MFAEnrollmentRequiredSerializer(serializers.Serializer):
    mfa_enrollment_required = serializers.BooleanField()
    enrollment_token = serializers.CharField(help_text='Accepted by the 2FA setup endpoints only.')
    expires_in = serializers.IntegerField()
