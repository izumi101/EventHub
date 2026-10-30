"""Request/response shapes of the auth endpoints, for the OpenAPI schema."""
from rest_framework import serializers

from .serializers import UserSerializer


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class AuthPayloadSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = TokenPairSerializer()


class EmailRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SendCodeResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    dev_code = serializers.CharField(
        required=False,
        help_text='Local development only (DEBUG with the console email backend).',
    )


class EmailCodeRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField()


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, help_text='Refresh token to revoke.')


class AvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.ImageField(help_text='JPEG, PNG, WebP or GIF, up to 5 MB.')


class IdentifierRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text='Username or email.')


class IdentifierCodeRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text='Username or email.')
    code = serializers.CharField()


class ResetTokenResponseSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    message = serializers.CharField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    new_password = serializers.CharField()
    new_password2 = serializers.CharField()


class ChangePasswordRequestSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()
    new_password2 = serializers.CharField()


class ChangePasswordResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    tokens = TokenPairSerializer(help_text='New pair for this device; other sessions are signed out.')
