"""DRF exception handler: turn leftover database conflicts into a 409
response instead of a 500 with a stack trace."""
import logging

from django.db import IntegrityError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ProtectedError):
        return Response(
            {'error': 'This item is referenced by payment or ticket records and cannot be deleted.'},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        logger.warning('Integrity error in %s: %s', context.get('view'), exc)
        return Response(
            {'error': 'This conflicts with existing data (duplicate or still in use).'},
            status=status.HTTP_409_CONFLICT,
        )
    return None
