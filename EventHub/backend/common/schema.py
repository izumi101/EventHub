"""Shared shapes for the OpenAPI schema.

Views that parse `request.data` by hand or return ad-hoc dicts describe
their contract with these serializers via `@extend_schema`; they are used
for documentation only and don't change what the views accept or return.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse
from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    error = serializers.CharField(help_text='Human-readable message; may change.')
    code = serializers.CharField(
        required=False,
        help_text='Stable machine-readable code, present where clients branch on it '
                  '(e.g. QUEUE_REQUIRED).',
    )


class DetailSerializer(serializers.Serializer):
    """DRF's own errors: authentication, permissions, not found, throttling."""
    detail = serializers.CharField()


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField()


ERROR = OpenApiResponse(ErrorSerializer, description='The request was refused; see `error`.')
VALIDATION_ERROR = OpenApiResponse(
    OpenApiTypes.OBJECT,
    description='Validation failed: field name → list of messages '
                '(`non_field_errors` for the request as a whole).',
)
UNAUTHENTICATED = OpenApiResponse(DetailSerializer, description='Missing or invalid access token.')
FORBIDDEN = OpenApiResponse(DetailSerializer, description='Not allowed for this user.')
NOT_FOUND = OpenApiResponse(DetailSerializer, description='No such object (or not visible to you).')
