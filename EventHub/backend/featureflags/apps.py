from django.apps import AppConfig


class FeatureFlagsConfig(AppConfig):
    name = 'featureflags'
    verbose_name = 'Feature flags'

    def ready(self):
        # Registers the system checks. Deliberately no Unleash client here:
        # it is created lazily in each worker process (see client.py).
        from . import checks  # noqa: F401
