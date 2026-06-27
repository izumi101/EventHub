from django.core.management.base import BaseCommand
from events.models import Event, SeatMap, EventSeat


class Command(BaseCommand):
    help = 'Generate seat maps for all events that don\'t have them.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate seat maps even if they exist',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)

        # Получаем события без seat_map или все, если force
        if force:
            events = Event.objects.all()
            SeatMap.objects.all().delete()
            EventSeat.objects.all().delete()
        else:
            # Только события без seat_map
            events = Event.objects.filter(seat_map__isnull=True)

        if not events.exists():
            self.stdout.write(self.style.SUCCESS('No events to process.'))
            return

        created_count = 0
        for event in events:
            # Генерируем seat_map: 6 рядов × 7 мест
            rows, cols = 6, 7

            # VIP зоны: ряды 1-2 (центр)
            # Standard: ряды 3-6
            layout = {
                'price_zones': {
                    'vip': [1, 2],
                    'standard': [3, 4, 5, 6],
                }
            }

            seat_map, created = SeatMap.objects.get_or_create(
                event=event,
                defaults={'rows': rows, 'cols': cols, 'layout': layout}
            )

            if created:
                # Создаём места
                for row in range(1, rows + 1):
                    # Определяем zone по ряду
                    if row <= 2:
                        zone = 'vip'
                    else:
                        zone = 'standard'

                    for col in range(1, cols + 1):
                        EventSeat.objects.create(
                            seat_map=seat_map,
                            row=row,
                            col=col,
                            price_zone=zone,
                            is_available=True,
                        )

                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created seat map for "{event.title}" ({rows}x{cols})')
                )
            else:
                self.stdout.write(f'- Seat map already exists for "{event.title}"')

        self.stdout.write(self.style.SUCCESS(f'\nTotal created: {created_count}'))
