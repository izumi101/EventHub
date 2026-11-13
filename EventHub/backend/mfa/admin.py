"""Read-only overview of users' second factors. Secrets and code hashes are
never shown; resetting a user goes through `manage.py mfa_reset` (logged)."""

from django.contrib import admin

from .models import MFAState, TOTPDevice, WebAuthnCredential


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TOTPDevice)
class TOTPDeviceAdmin(_ReadOnlyAdmin):
    list_display = ('user', 'confirmed', 'created_at', 'confirmed_at', 'last_used_at')
    list_filter = ('confirmed',)
    search_fields = ('user__username', 'user__email')
    exclude = ('encrypted_secret', 'last_used_step')


@admin.register(WebAuthnCredential)
class WebAuthnCredentialAdmin(_ReadOnlyAdmin):
    list_display = ('user', 'name', 'backed_up', 'sign_count', 'created_at', 'last_used_at')
    search_fields = ('user__username', 'user__email', 'name')
    exclude = ('public_key', 'credential_id')


@admin.register(MFAState)
class MFAStateAdmin(_ReadOnlyAdmin):
    list_display = ('user', 'failed_attempts', 'locked_until', 'last_failure_at')
    search_fields = ('user__username', 'user__email')
    exclude = ('webauthn_user_handle',)
