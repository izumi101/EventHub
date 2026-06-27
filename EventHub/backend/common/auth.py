from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework_simplejwt.tokens import RefreshToken

PASSWORD_MIN_LENGTH = 8


def get_user_by_identifier(identifier: str):
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        return None
    return User.objects.filter(
        Q(email=normalized_identifier) | Q(username=normalized_identifier)
    ).first()


def password_meets_policy(password: str) -> tuple[bool, str | None]:
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f'Password must be at least {PASSWORD_MIN_LENGTH} characters.'
    if not any(char.isdigit() for char in password):
        return False, 'Password must contain at least one digit.'
    return True, None


def create_jwt_payload(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
