from django.core.management.base import BaseCommand
from events.models import Event
from events.search import index_event


class Command(BaseCommand):
    help = 'Generate semantic embeddings for all events (needed for semantic search).'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Re-index already-embedded events')

    def handle(self, *args, **options):
        force = options['force']
        qs = Event.objects.all() if force else Event.objects.filter(embedding__isnull=True)
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('All events already indexed.'))
            return

        self.stdout.write(f'Indexing {total} events…')
        ok = 0
        for event in qs.select_related('category'):
            try:
                index_event(event)
                ok += 1
                self.stdout.write(f'  ✓ [{ok}/{total}] {event.title}')
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'  ✗ {event.title}: {exc}'))

        self.stdout.write(self.style.SUCCESS(f'\nDone. {ok}/{total} events indexed.'))
