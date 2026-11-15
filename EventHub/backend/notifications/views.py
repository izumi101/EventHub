from contextlib import contextmanager

from django.db import transaction
from django.utils import translation
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.schema import UNAUTHENTICATED, VALIDATION_ERROR, ErrorSerializer

from . import types, unsubscribe
from .models import NotificationPreference
from .serializers import (
    NotificationPreferencesSerializer,
    NotificationPreferencesUpdateSerializer,
    UnsubscribeSerializer,
    UnsubscribeTokenSerializer,
)


@contextmanager
def request_language(request):
    """Labels and descriptions in the request's `Accept-Language` (en, ru,
    kk). Scoped to these responses: there is no LocaleMiddleware, so every
    other API text (errors included) stays English."""
    with translation.override(translation.get_language_from_request(request)):
        yield


def _preferences_payload(user, preference: NotificationPreference) -> dict:
    return {
        'email_address': user.email or '',
        'language': preference.language,
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


def _switch_off(user, type_key: str) -> None:
    with transaction.atomic():
        preference, _ = NotificationPreference.objects.select_for_update().get_or_create(user=user)
        disabled = set(preference.email_disabled or [])
        if type_key in disabled:
            return
        disabled.add(type_key)
        preference.email_disabled = sorted(disabled)
        preference.save(update_fields=['email_disabled', 'updated_at'])


class NotificationPreferencesView(APIView):
    """The signed-in user's notification email preferences and language."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        responses={200: NotificationPreferencesSerializer, 401: UNAUTHENTICATED},
    )
    def get(self, request):
        preference = NotificationPreference.objects.filter(user=request.user).first() or NotificationPreference(
            user=request.user
        )
        with request_language(request):
            return Response(_preferences_payload(request.user, preference))

    @extend_schema(
        request=NotificationPreferencesUpdateSerializer,
        responses={200: NotificationPreferencesSerializer, 400: VALIDATION_ERROR, 401: UNAUTHENTICATED},
    )
    def patch(self, request):
        serializer = NotificationPreferencesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes = serializer.validated_data
        with transaction.atomic():
            preference, _ = NotificationPreference.objects.select_for_update().get_or_create(user=request.user)
            disabled = set(preference.email_disabled or [])
            for key, enabled in changes.get('email', {}).items():
                if enabled:
                    disabled.discard(key)
                else:
                    disabled.add(key)
            preference.email_disabled = sorted(disabled)
            if 'language' in changes:
                preference.language = changes['language']
            preference.save(update_fields=['email_disabled', 'language', 'updated_at'])
        with request_language(request):
            return Response(_preferences_payload(request.user, preference))


TOKEN_PARAMETER = OpenApiParameter(
    'token',
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    required=False,
    description='The signed token from the email (`List-Unsubscribe` URL or footer link).',
)
INVALID_TOKEN = OpenApiResponse(
    ErrorSerializer, description='Missing, malformed or tampered token (one message for every case).'
)


class UnsubscribeView(APIView):
    """One-click unsubscribe from one optional email type (RFC 8058).

    No sign-in: the signed token in the email identifies the user and the
    type. `GET` only describes the link (link scanners and mail previews
    follow links; nothing changes). `POST` switches that email off; it is
    idempotent. Mail providers POST `List-Unsubscribe=One-Click` as a form
    to the `List-Unsubscribe` URL, which carries the token in the query.
    """

    authentication_classes: list = []  # no session, so no CSRF; the token is the credential
    permission_classes = [AllowAny]
    parser_classes = [FormParser, JSONParser, MultiPartParser]
    # The default throttles (per-scope and per-IP) apply; see settings.
    throttle_scope = 'unsubscribe'

    def _read(self, request, *, body: bool):
        token = request.query_params.get('token')
        if not token and body:
            getter = getattr(request.data, 'get', None)
            token = getter('token') if getter else None
        try:
            return unsubscribe.read_token(token)
        except unsubscribe.InvalidToken:
            return None

    @staticmethod
    def _invalid():
        return Response({'error': 'This unsubscribe link is invalid.'}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _payload(request, type_key: str) -> dict:
        with request_language(request):
            return {'type': type_key, 'label': str(types.get(type_key).label)}

    @extend_schema(
        operation_id='notifications_unsubscribe_retrieve',
        parameters=[TOKEN_PARAMETER],
        auth=[],
        responses={200: UnsubscribeSerializer, 400: INVALID_TOKEN},
    )
    def get(self, request):
        found = self._read(request, body=False)
        if found is None:
            return self._invalid()
        _user, type_key = found
        return Response(self._payload(request, type_key))

    @extend_schema(
        operation_id='notifications_unsubscribe_create',
        parameters=[TOKEN_PARAMETER],
        request=UnsubscribeTokenSerializer,
        auth=[],
        responses={200: UnsubscribeSerializer, 400: INVALID_TOKEN},
    )
    def post(self, request):
        found = self._read(request, body=True)
        if found is None:
            return self._invalid()
        user, type_key = found
        _switch_off(user, type_key)
        return Response(self._payload(request, type_key))
