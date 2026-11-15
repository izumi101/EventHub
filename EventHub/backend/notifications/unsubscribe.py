"""One-click unsubscribe tokens (RFC 8058).

An optional email carries a link that switches that one email type off for
its recipient without signing in. The token is the user id and the type key,
signed with the secret key under a dedicated salt: it can't be forged or
altered, and it never expires (an old email's link keeps working, like the
preferences page would). It reveals nothing but what the recipient already
knows (their own id and the type of email they got).
"""

from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core import signing

from . import types
from .messages import frontend_url

SALT = 'notifications.unsubscribe.v1'
# The API endpoint mail providers POST to (List-Unsubscribe); the frontend
# nginx proxies /api to the backend, so it lives on the public origin.
API_PATH = '/api/v1/notifications/unsubscribe/'
# The page the footer link opens: shows the type and asks for a click.
PAGE_PATH = '/unsubscribe'


class InvalidToken(Exception):
    """The token is malformed, tampered with or names no unsubscribable email."""


def make_token(user, type_key: str) -> str:
    return signing.Signer(salt=SALT).sign_object([user.pk, type_key], compress=True)


def read_token(token: str) -> tuple[User, str]:
    """(user, type_key) of a valid token; raises InvalidToken otherwise.

    Every failure raises the same error, so a caller can't tell a wrong
    signature from a deleted account."""
    if not token or not isinstance(token, str) or len(token) > 512:
        raise InvalidToken
    try:
        payload = signing.Signer(salt=SALT).unsign_object(token)
    except (signing.BadSignature, ValueError, TypeError):
        raise InvalidToken from None
    if not (isinstance(payload, list) and len(payload) == 2):
        raise InvalidToken
    user_id, type_key = payload
    if not isinstance(user_id, int) or type_key not in types.EMAIL_OPTIONAL_TYPES:
        raise InvalidToken
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise InvalidToken
    return user, type_key


def _with_token(path: str, token: str) -> str:
    return frontend_url(f'{path}?{urlencode({"token": token})}')


def api_url(token: str) -> str:
    """The `List-Unsubscribe` target (POST: one click, GET: read-only)."""
    return _with_token(API_PATH, token)


def page_url(token: str) -> str:
    """The footer link: a page that confirms before switching anything off."""
    return _with_token(PAGE_PATH, token)
