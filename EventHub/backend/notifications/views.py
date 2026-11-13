from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.schema import UNAUTHENTICATED, VALIDATION_ERROR

from . import types
from .models import NotificationPreference
from .serializers import NotificationPreferencesSerializer, NotificationPreferencesUpdateSerializer


def _preferences_payload(user, preference: NotificationPreference) -> dict:
    return {
        'email_address': user.email or '',
        'types': [
            {
                'type': spec.key,
                'label': str(spec.label),
                'description': str(spec.description),
                'email_enabled': preference.email_enabled(spec.key),
                'email_optional': spec.email_optional,
            }
            for spec in types.TYPES.values()
            if spec.sends_email
        ],
    }


class NotificationPreferencesView(APIView):
    """The signed-in user's notification email preferences."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        responses={200: NotificationPreferencesSerializer, 401: UNAUTHENTICATED},
    )
    def get(self, request):
        preference = NotificationPreference.objects.filter(user=request.user).first() or NotificationPreference(
            user=request.user
        )
        return Response(_preferences_payload(request.user, preference))

    @extend_schema(
        request=NotificationPreferencesUpdateSerializer,
        responses={200: NotificationPreferencesSerializer, 400: VALIDATION_ERROR, 401: UNAUTHENTICATED},
    )
    def patch(self, request):
        serializer = NotificationPreferencesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            preference, _ = NotificationPreference.objects.select_for_update().get_or_create(user=request.user)
            disabled = set(preference.email_disabled or [])
            for key, enabled in serializer.validated_data['email'].items():
                if enabled:
                    disabled.discard(key)
                else:
                    disabled.add(key)
            preference.email_disabled = sorted(disabled)
            preference.save(update_fields=['email_disabled', 'updated_at'])
        return Response(_preferences_payload(request.user, preference))
