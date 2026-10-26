from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

PASSWORD_MIN_LENGTH = 8


def get_user_by_identifier(identifier: str):
    """Resolve a login/reset identifier to exactly one user.

    Anything with an '@' is treated as an email first: usernames may not
    contain '@' (see validate_username), so an attacker can't register the
    username "victim@mail.com" to capture the victim's email logins. Accounts
    created before that rule can still sign in with their username, but only
    when no account owns that email.
    """
    normalized = (identifier or '').strip()
    if not normalized:
        return None
    if '@' in normalized:
        matches = list(User.objects.filter(email__iexact=normalized)[:2])
        if len(matches) == 1:
            return matches[0]
        if matches:  # ambiguous: never guess between two accounts
            return None
    return User.objects.filter(username=normalized).first()


def validate_username(value: str) -> str:
    if '@' in value:
        raise ValueError('Usernames cannot contain "@".')
    if User.objects.filter(username__iexact=value).exists():
        raise ValueError('Username already exists.')
    return value


def email_in_use(email: str) -> bool:
    return User.objects.filter(email__iexact=(email or '').strip()).exists()


def password_meets_policy(password: str, user=None) -> tuple[bool, str | None]:
    """Project rule (8+ chars incl. a digit) plus Django's AUTH_PASSWORD_VALIDATORS."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f'Password must be at least {PASSWORD_MIN_LENGTH} characters.'
    if not any(char.isdigit() for char in password):
        return False, 'Password must contain at least one digit.'
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return False, ' '.join(exc.messages)
    return True, None


def revoke_all_refresh_tokens(user) -> None:
    """Sign the user out everywhere: blacklist every refresh token issued to
    them (after a password change or reset a stolen token must stop working)."""
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    tokens = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=t) for t in tokens], ignore_conflicts=True,
    )


def create_jwt_payload(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
