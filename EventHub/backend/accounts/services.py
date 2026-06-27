import logging
import secrets

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailVerificationCode, PasswordResetCode
from common.auth import get_user_by_identifier, password_meets_policy

logger = logging.getLogger(__name__)

WELCOME_FROM_EMAIL = 'EventHub Team <eventhub.supporting@gmail.com>'
VERIFICATION_FROM_EMAIL = 'EventHub <eventhub.supporting@gmail.com>'


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

    try:
        send_mail(
            'Welcome to EventHub 🎉',
            'Hey there 👋\n\nWelcome to EventHub — your space for discovering, creating, and sharing amazing events.\n\nWe\'re really excited to have you here 🚀\n\nFrom now on, you can explore events around you, join communities, and never miss something interesting again.\n\nThis is just the beginning — let\'s build something awesome together 🔥\n\nSee you inside,\nEventHub Team',
            WELCOME_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning('Welcome email failed for user %s: %s', user.username, exc)

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

    try:
        send_mail(
            'Your EventHub organizer account',
            f'Hello!\n\nAn administrator created an organizer account for you on EventHub.\n\nUsername: {user.username}\n\nSign in and start creating events. Remember to change your password after the first login.\n\nEventHub Team',
            WELCOME_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning('Organizer welcome email failed for %s: %s', user.username, exc)

    return user


def send_registration_code(email: str) -> EmailVerificationCode:
    if User.objects.filter(email=email).exists():
        raise ValueError('A user with this email already exists')

    verification = EmailVerificationCode.create_for_email(email)
    send_mail(
        'EventHub — Registration Verification Code',
        f'Your verification code is: {verification.code}\n\nThis code expires in 15 minutes.',
        VERIFICATION_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    return verification


def verify_registration_code(email: str, code: str) -> EmailVerificationCode:
    verification = EmailVerificationCode.objects.filter(email=email, code=code, is_used=False).first()
    if not verification or verification.is_expired:
        raise ValueError('Invalid or expired verification code.')
    return verification


def login_user(identifier: str, password: str):
    user_obj = get_user_by_identifier(identifier)
    if not user_obj:
        return None

    return authenticate(username=user_obj.username, password=password)


def request_password_reset(identifier: str):
    user = get_user_by_identifier(identifier)
    if not user:
        return None

    reset_code = PasswordResetCode.create_for_user(user)
    send_mail(
        'EventHub — Password Reset Code',
        f'Your password reset code is: {reset_code.code}\n\nThis code expires in 15 minutes.\n\nIf you did not request this, please ignore this email.',
        VERIFICATION_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )
    return reset_code


def verify_password_reset_code(identifier: str, code: str):
    user = get_user_by_identifier(identifier)
    if not user:
        raise ValueError('Invalid code.')

    reset_entry = PasswordResetCode.objects.filter(
        user=user, code=code, is_used=False
    ).first()

    if not reset_entry or reset_entry.is_expired:
        raise ValueError('Invalid or expired code.')

    reset_token = secrets.token_urlsafe(48)
    reset_entry.reset_token = reset_token
    reset_entry.save(update_fields=['reset_token'])
    return reset_entry


def confirm_password_reset(reset_token: str, new_password: str, new_password2: str):
    if new_password != new_password2:
        raise ValueError('Passwords do not match.')

    is_valid, message = password_meets_policy(new_password)
    if not is_valid:
        raise ValueError(message)

    reset_entry = PasswordResetCode.objects.filter(
        reset_token=reset_token, is_used=False
    ).first()

    if not reset_entry or reset_entry.is_expired:
        raise ValueError('Invalid or expired reset token.')

    user = reset_entry.user
    user.set_password(new_password)
    user.save(update_fields=['password'])

    reset_entry.is_used = True
    reset_entry.save(update_fields=['is_used'])
    return user
