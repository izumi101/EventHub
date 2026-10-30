import logging
import secrets

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from rest_framework_simplejwt.tokens import RefreshToken

from jobs.handlers import enqueue_email

from .models import MAX_CODE_ATTEMPTS, EmailVerificationCode, PasswordResetCode
from common.auth import (
    email_in_use,
    get_user_by_identifier,
    password_meets_policy,
    revoke_all_refresh_tokens,
)

logger = logging.getLogger(__name__)

INVALID_CODE_MESSAGE = 'Invalid or expired code.'


def _code_matches(model, entry, code) -> bool:
    """Check a 6-digit code against `entry`, counting the attempt *before*
    comparing: parallel guesses can't exceed MAX_CODE_ATTEMPTS, and the code
    is burned once the budget is spent."""
    if entry is None or entry.is_used or entry.is_expired:
        return False
    counted = model.objects.filter(
        pk=entry.pk,
        is_used=False,
        attempts__lt=MAX_CODE_ATTEMPTS,
    ).update(attempts=F('attempts') + 1)
    if not counted:
        return False
    if secrets.compare_digest(str(entry.code), str(code or '').strip()):
        return True
    model.objects.filter(pk=entry.pk, attempts__gte=MAX_CODE_ATTEMPTS).update(is_used=True)
    return False


def build_auth_payload(user):
    refresh = RefreshToken.for_user(user)
    from .serializers import UserSerializer

    return {
        'user': UserSerializer(user).data,
        'tokens': {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        },
    }


@transaction.atomic
def register_user(validated_data):
    verification = validated_data.pop('_verification', None)
    validated_data.pop('password2', None)
    first_name = validated_data.pop('first_name', '')
    last_name = validated_data.pop('last_name', '')
    phone = validated_data.pop('phone', '')

    user = User.objects.create_user(
        username=validated_data['username'],
        email=validated_data['email'],
        password=validated_data['password'],
        first_name=first_name,
        last_name=last_name,
    )

    # Self-registration always creates an attendee; organizer accounts are
    # provisioned by an administrator via create_organizer().
    profile = user.profile
    profile.phone = phone
    profile.role = 'attendee'
    profile.save()

    if verification:
        verification.is_used = True
        verification.save(update_fields=['is_used'])

    enqueue_email(
        'Welcome to EventHub 🎉',
        "Hey there 👋\n\nWelcome to EventHub — your space for discovering, creating, and sharing amazing events.\n\nWe're really excited to have you here 🚀\n\nFrom now on, you can explore events around you, join communities, and never miss something interesting again.\n\nThis is just the beginning — let's build something awesome together 🔥\n\nSee you inside,\nEventHub Team",
        user.email,
    )

    return user


@transaction.atomic
def create_organizer(validated_data):
    """Admin-only: provision an organizer account (no email verification)."""
    user = User.objects.create_user(
        username=validated_data['username'],
        email=validated_data['email'],
        password=validated_data['password'],
        first_name=validated_data.get('first_name', ''),
        last_name=validated_data.get('last_name', ''),
    )

    profile = user.profile
    profile.phone = validated_data.get('phone', '')
    profile.role = 'organizer'
    profile.save()

    enqueue_email(
        'Your EventHub organizer account',
        f'Hello!\n\nAn administrator created an organizer account for you on EventHub.\n\nUsername: {user.username}\n\nSign in and start creating events. Remember to change your password after the first login.\n\nEventHub Team',
        user.email,
    )

    return user


@transaction.atomic
def send_registration_code(email: str):
    """Email a sign-up code. Returns the code row, or None when the address
    already has an account — the API answers the same in both cases so it
    can't be used to find out who is registered; the owner gets a heads-up."""
    if email_in_use(email):
        enqueue_email(
            'EventHub — sign-up attempt',
            'Someone tried to create an EventHub account with this email address, '
            'but you already have one. If it was you, sign in or reset your password. '
            'Otherwise you can ignore this email.',
            email,
        )
        return None

    verification = EmailVerificationCode.create_for_email(email)
    enqueue_email(
        'EventHub — Registration Verification Code',
        f'Your verification code is: {verification.code}\n\nThis code expires in 15 minutes.',
        email,
    )
    return verification


def verify_registration_code(email: str, code: str) -> EmailVerificationCode:
    verification = (
        EmailVerificationCode.objects.filter(email__iexact=(email or '').strip(), is_used=False)
        .order_by('-created_at')
        .first()
    )
    if not _code_matches(EmailVerificationCode, verification, code):
        raise ValueError('Invalid or expired verification code.')
    return verification


def login_user(identifier: str, password: str):
    user_obj = get_user_by_identifier(identifier)
    if not user_obj:
        return None

    return authenticate(username=user_obj.username, password=password)


@transaction.atomic
def request_password_reset(identifier: str):
    user = get_user_by_identifier(identifier)
    if not user:
        return None

    reset_code = PasswordResetCode.create_for_user(user)
    enqueue_email(
        'EventHub — Password Reset Code',
        f'Your password reset code is: {reset_code.code}\n\nThis code expires in 15 minutes.\n\nIf you did not request this, please ignore this email.',
        user.email,
    )
    return reset_code


def verify_password_reset_code(identifier: str, code: str):
    user = get_user_by_identifier(identifier)
    reset_entry = None
    if user is not None:
        reset_entry = PasswordResetCode.objects.filter(user=user, is_used=False).order_by('-created_at').first()
    # Same answer for "no such account" and "wrong code" (no enumeration).
    if not _code_matches(PasswordResetCode, reset_entry, code):
        raise ValueError(INVALID_CODE_MESSAGE)

    reset_token = secrets.token_urlsafe(48)
    reset_entry.reset_token = reset_token
    reset_entry.save(update_fields=['reset_token'])
    return reset_entry


@transaction.atomic
def confirm_password_reset(reset_token: str, new_password: str, new_password2: str):
    if new_password != new_password2:
        raise ValueError('Passwords do not match.')

    reset_entry = (
        (PasswordResetCode.objects.select_for_update().filter(reset_token=reset_token, is_used=False).first())
        if reset_token
        else None
    )

    if not reset_entry or reset_entry.is_expired:
        raise ValueError('Invalid or expired reset token.')

    user = reset_entry.user
    is_valid, message = password_meets_policy(new_password, user)
    if not is_valid:
        raise ValueError(message)

    user.set_password(new_password)
    user.save(update_fields=['password'])
    revoke_all_refresh_tokens(user)

    reset_entry.is_used = True
    reset_entry.save(update_fields=['is_used'])
    return user


@transaction.atomic
def change_password(user, old_password: str, new_password: str, new_password2: str):
    """Returns a fresh token pair for the current device; every other session
    (all previously issued refresh tokens) is signed out."""
    if not user.check_password(old_password):
        raise ValueError('Current password is incorrect.')
    if new_password != new_password2:
        raise ValueError('Passwords do not match.')
    is_valid, message = password_meets_policy(new_password, user)
    if not is_valid:
        raise ValueError(message)
    user.set_password(new_password)
    user.save(update_fields=['password'])
    revoke_all_refresh_tokens(user)
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}
