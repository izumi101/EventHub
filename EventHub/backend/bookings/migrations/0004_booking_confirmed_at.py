"""`Booking.confirmed_at`: when a group booking was paid.

A booking is created `holding` and confirmed when the payment arrives, up to
the 10-minute hold later, so `created_at` can be the day before. The organizer
sales chart counts a booking's money on the day it was confirmed.

Backfill, for confirmed and refunded bookings: `paid_at` of the booking's
payment when it has one, else `created_at`. Reverse: the data step has nothing
to undo; the schema operation drops the column.
"""

from django.db import migrations, models
from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import Coalesce


def backfill_confirmed_at(apps, schema_editor=None):
    Booking = apps.get_model('bookings', 'Booking')
    Payment = apps.get_model('payments', 'Payment')
    paid = Payment.objects.filter(booking=OuterRef('pk'), paid_at__isnull=False).values('paid_at')[:1]
    return Booking.objects.filter(status__in=['confirmed', 'refunded'], confirmed_at__isnull=True).update(
        confirmed_at=Coalesce(Subquery(paid), F('created_at'))
    )


class Migration(migrations.Migration):
    dependencies = [
        ('bookings', '0003_booking_refunds'),
        ('payments', '0008_payment_paid_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_confirmed_at, migrations.RunPython.noop, elidable=False),
    ]
