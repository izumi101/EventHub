from events.models import Event, Category
from django.utils import timezone
from datetime import timedelta

# Update Music event to be in the future
music_event = Event.objects.filter(category__name__icontains='Music').first()
if music_event:
    music_event.date = timezone.now() + timedelta(days=5)
    music_event.save()
    print(f"Updated Music event: {music_event.title} to {music_event.date}")
else:
    print("Music event not found")
