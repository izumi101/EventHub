from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from common.choices import RoleChoices
from common.codes import generate_numeric_code


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.ATTENDEE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} Profile'


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, **kwargs):
    profile, _ = UserProfile.objects.get_or_create(user=instance)
    profile.save()


class PasswordResetCode(models.Model):
    """Stores a 6-digit verification code for password reset."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_codes')
    code = models.CharField(max_length=6)
    reset_token = models.CharField(max_length=64, blank=True, null=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Reset code for {self.user.username} ({self.code})'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def create_for_user(cls, user):
        # Invalidate previous codes
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        return cls.objects.create(
            user=user,
            code=generate_numeric_code(),
            expires_at=timezone.now() + timedelta(minutes=15)
        )


class EmailVerificationCode(models.Model):
    """Stores a 6-digit verification code for email during registration."""
    email = models.EmailField()
    code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Verification code for {self.email} ({self.code})'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def create_for_email(cls, email):
        # Invalidate previous codes
        cls.objects.filter(email=email, is_used=False).update(is_used=True)
        return cls.objects.create(
            email=email,
            code=generate_numeric_code(),
            expires_at=timezone.now() + timedelta(minutes=15)
        )
