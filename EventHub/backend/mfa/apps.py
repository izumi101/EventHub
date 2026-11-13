from django.apps import AppConfig


class MfaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mfa'
    verbose_name = 'Two-factor authentication'

    def ready(self):
        from . import (
            schema,  # noqa: F401  (OpenAPI extensions)
            signals,  # noqa: F401  (connects the receivers)
        )
