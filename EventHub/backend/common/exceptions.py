"""Domain errors, and a DRF exception handler that turns leftover database
conflicts into a 409 response instead of a 500 with a stack trace."""

import logging

from django.db import IntegrityError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class DomainError(ValueError):
    """A business-rule refusal with a stable `code` clients can branch on;
    the message is for people and may change. A ValueError, so existing
    `except ValueError` handlers keep working."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def error_response(exc: ValueError, status_code=status.HTTP_400_BAD_REQUEST) -> Response:
    body = {'error': str(exc)}
    if isinstance(exc, DomainError):
        body['code'] = exc.code
    return Response(body, status=status_code)


def exception_handler(exc, context):
    from mfa.exceptions import MFAError, TokenWithoutMFA

    if isinstance(exc, MFAError):
        # Same shape as every other refusal, plus the stable code the SPA
        # branches on (mfa_step_up_required, mfa_locked, ...).
        body = {'error': str(exc.detail), 'code': exc.mfa_code, **exc.extra}
        headers = {}
        if exc.extra.get('retry_after'):
            headers['Retry-After'] = str(exc.extra['retry_after'])
        return Response(body, status=exc.status_code, headers=headers)
    response = drf_exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, TokenWithoutMFA) and isinstance(response.data, dict):
            response.data['code'] = 'mfa_required'
        return response
    if isinstance(exc, DomainError):
        return error_response(exc)
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
