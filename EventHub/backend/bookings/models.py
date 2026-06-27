import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from events.models import Event, EventSeat


class Booking(models.Model):
    """A group reservation of one or more seats for an event."""

    class Status(models.TextChoices):
        HOLDING = 'holding', 'Holding'        # seats held, awaiting payment
        CONFIRMED = 'confirmed', 'Confirmed'  # paid
        CANCELLED = 'cancelled', 'Cancelled'  # released by owner
        EXPIRED = 'expired', 'Expired'        # hold timed out

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='bookings')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.HOLDING)

    # Shareable invite link token (friends use it to claim a seat)
    share_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    hold_expires_at = models.DateTimeField(null=True, blank=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Booking {self.id} · {self.event.title} · {self.status}'

    @property
    def is_expired(self) -> bool:
        return (
            self.status == self.Status.HOLDING
            and self.hold_expires_at is not None
            and self.hold_expires_at < timezone.now()
        )

    @property
    def seat_count(self) -> int:
        return self.seats.count()

    @property
    def total_price(self) -> Decimal:
        total = self.seats.aggregate(s=models.Sum('price'))['s']
        return total or Decimal('0.00')


class BookingSeat(models.Model):
    """One seat inside a booking — also acts as an individual ticket."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='seats')
    seat = models.OneToOneField(EventSeat, on_delete=models.CASCADE, related_name='booking_seat')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Who sits here — filled by the owner or a friend via the share link
    attendee_name = models.CharField(max_length=120, blank=True)
    claimed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='claimed_seats'
    )

    # Ticket / QR
    ticket_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    is_checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seat__row', 'seat__col']

    def __str__(self):
        return f'{self.booking_id} · seat {self.seat.row}-{self.seat.col}'
