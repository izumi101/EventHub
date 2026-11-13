from rest_framework import serializers

from . import types


class NotificationTypePreferenceSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=types.CHOICES, read_only=True)
    label = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    email_enabled = serializers.BooleanField(read_only=True)
    email_optional = serializers.BooleanField(
        read_only=True, help_text='False: the email is always sent and cannot be switched off.'
    )


class NotificationPreferencesSerializer(serializers.Serializer):
    """Email preferences per notification type. In-app notifications are
    always on; sign-up codes, password reset and other security emails are
    not listed: they are always sent."""

    email_address = serializers.EmailField(read_only=True, help_text='Where emails go (empty: none are sent).')
    types = NotificationTypePreferenceSerializer(many=True, read_only=True)


class NotificationPreferencesUpdateSerializer(serializers.Serializer):
    email = serializers.DictField(
        child=serializers.BooleanField(),
        help_text=(
            'Type key → email on/off, e.g. {"event_reminder": false}. Only the types listed with '
            '`email_optional: true` can be changed; types not mentioned keep their setting.'
        ),
    )

    def validate_email(self, value):
        not_allowed = sorted(set(value) - set(types.EMAIL_OPTIONAL_TYPES))
        if not_allowed:
            raise serializers.ValidationError(
                f'These notification emails cannot be switched: {", ".join(not_allowed)}.'
            )
        return value
