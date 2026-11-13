"""Keep the cached "has 2FA" answer (policy.mfa_enabled) in step with the factors."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import TOTPDevice, WebAuthnCredential
from .policy import forget_mfa_enabled


@receiver(post_save, sender=TOTPDevice)
@receiver(post_delete, sender=TOTPDevice)
@receiver(post_save, sender=WebAuthnCredential)
@receiver(post_delete, sender=WebAuthnCredential)
def _factors_changed(sender, instance, **kwargs):
    forget_mfa_enabled(instance.user_id)
