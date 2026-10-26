from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import IntegrityError
from .models import UserProfile
from common.auth import email_in_use, password_meets_policy, validate_username as check_username
from common.choices import RoleChoices
from .services import register_user, verify_registration_code


# ---- Serializer (manual) ---- #
class RegisterSerializer(serializers.Serializer):
    """Manual Serializer for user registration."""
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    # Role is intentionally NOT accepted here — everyone registers as an
    # attendee; organizer accounts are created by an administrator.
    verification_code = serializers.CharField(write_only=True, required=True, min_length=6, max_length=6)

    def validate_username(self, value):
        try:
            return check_username(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate_password(self, value):
        is_valid, message = password_meets_policy(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})

        # The code proves the caller owns the address; only then is it safe
        # to say whether the address is taken (no account enumeration).
        try:
            data['_verification'] = verify_registration_code(data['email'], data['verification_code'])
        except ValueError as exc:
            raise serializers.ValidationError({'verification_code': str(exc)})
        if email_in_use(data['email']):
            raise serializers.ValidationError({'email': 'Email already registered.'})

        is_valid, message = password_meets_policy(
            data['password'], User(username=data['username'], email=data['email']),
        )
        if not is_valid:
            raise serializers.ValidationError({'password': message})
        return data

    def create(self, validated_data):
        try:
            return register_user(validated_data)
        except IntegrityError:
            # Lost a race with a simultaneous sign-up (DB unique index).
            raise serializers.ValidationError({'email': 'Email already registered.'})


# ---- Serializer (manual) ---- #
class LoginSerializer(serializers.Serializer):
    """Manual Serializer for login."""
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


# ---- Serializer (manual) ---- #
class OrganizerCreateSerializer(serializers.Serializer):
    """Admin-only: create an organizer account directly (no email code)."""
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_username(self, value):
        try:
            return check_username(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate_email(self, value):
        if email_in_use(value):
            raise serializers.ValidationError('Email already registered.')
        return value

    def validate_password(self, value):
        is_valid, message = password_meets_policy(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value

    def create(self, validated_data):
        from .services import create_organizer
        try:
            return create_organizer(validated_data)
        except IntegrityError:
            raise serializers.ValidationError({'email': 'Email already registered.'})


# ---- ModelSerializer ---- #
class UserProfileSerializer(serializers.ModelSerializer):
    # Read-only: users cannot promote themselves to organizer — only an
    # administrator can (see AdminCreateOrganizerView).
    role = serializers.ChoiceField(choices=RoleChoices.choices, read_only=True)

    class Meta:
        model = UserProfile
        fields = ['bio', 'phone', 'avatar', 'location', 'website', 'role']


# ---- ModelSerializer ---- #
class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile', 'is_staff', 'is_superuser']
        read_only_fields = ['id', 'username', 'email', 'is_staff', 'is_superuser']

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.save()

        profile, _ = UserProfile.objects.get_or_create(user=instance)
        for attr, value in profile_data.items():
            setattr(profile, attr, value)
        profile.save()
        return instance
