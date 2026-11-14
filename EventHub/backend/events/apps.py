from django.apps import AppConfig
from django.db.models.signals import post_migrate


class EventsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'events'

    def ready(self):
        from common.db_schemas import arrange_after_migrate

        # Moves new tables into their domain schema (docs/DATABASE_SCHEMAS.md).
        # post_migrate is sent once per app after all migrations ran; this
        # app's signal is enough to run it once per migrate (and per flush).
        post_migrate.connect(arrange_after_migrate, sender=self, dispatch_uid='common.db_schemas.arrange')
