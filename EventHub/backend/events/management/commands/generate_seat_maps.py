from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from events.models import Event, EventSeat, Registration, SeatMap


class Command(BaseCommand):
    help = "Generate seat maps for events that don't have them."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate the seat map of the events given with --event (refused when any seat is sold or held).',
        )
        parser.add_argument(
            '--event',
            type=int,
            action='append',
            dest='event_ids',
            default=[],
            help='Only process this event id (repeatable). Required with --force.',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        event_ids = options.get('event_ids') or []

        if force:
            if not event_ids:
                raise CommandError('--force needs at least one --event ID: it never wipes every seat map.')
            events = Event.objects.filter(id__in=event_ids)
            with transaction.atomic():
                for event in events:
                    sold = (
                        Registration.objects.filter(event=event, seat__isnull=False).exists()
                        or EventSeat.objects.filter(seat_map__event=event, booking_seat__isnull=False).exists()
                    )
                    if sold:
                        raise CommandError(
                            f'Event {event.id} has seats sold or on hold — refusing to regenerate its map.'
                        )
                    SeatMap.objects.filter(event=event).delete()
        else:
            # Only events without a seat map
            events = Event.objects.filter(seat_map__isnull=True)
            if event_ids:
                events = events.filter(id__in=event_ids)

        if not events.exists():
            self.stdout.write(self.style.SUCCESS('No events to process.'))
            return

        created_count = 0
        for event in events:
            # Seat map: 6 rows × 7 seats
            rows, cols = 6, 7

            # VIP: rows 1-2 (center)
            # Standard: rows 3-6
            layout = {
                'price_zones': {
                    'vip': [1, 2],
                    'standard': [3, 4, 5, 6],
                }
            }

            seat_map, created = SeatMap.objects.get_or_create(
                event=event, defaults={'rows': rows, 'cols': cols, 'layout': layout}
            )

            if created:
                # Create the seats
                for row in range(1, rows + 1):
                    zone = 'vip' if row <= 2 else 'standard'

                    for col in range(1, cols + 1):
                        EventSeat.objects.create(
                            seat_map=seat_map,
                            row=row,
                            col=col,
                            price_zone=zone,
                            is_available=True,
                        )

                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Created seat map for "{event.title}" ({rows}x{cols})'))
            else:
                self.stdout.write(f'- Seat map already exists for "{event.title}"')

        self.stdout.write(self.style.SUCCESS(f'\nTotal created: {created_count}'))
