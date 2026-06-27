from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, EmailVerificationCode
from common.auth import password_meets_policy
from common.choices import RoleChoices
from .services import register_user


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
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Username already exists.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Email already registered.')
        return value

    def validate_password(self, value):
        is_valid, message = password_meets_policy(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})

        email = data.get('email')
        code = data.get('verification_code')
        if email and code:
            verification = EmailVerificationCode.objects.filter(email=email, code=code, is_used=False).first()
            if not verification or verification.is_expired:
                raise serializers.ValidationError({'verification_code': 'Invalid or expired verification code.'})
            data['_verification'] = verification
        
        return data

    def create(self, validated_data):
        return register_user(validated_data)


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
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Username already exists.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('Email already registered.')
        return value

    def validate_password(self, value):
        is_valid, message = password_meets_policy(value)
        if not is_valid:
            raise serializers.ValidationError(message)
        return value

    def create(self, validated_data):
        from .services import create_organizer
        return create_organizer(validated_data)


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
