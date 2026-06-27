import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from pgvector.django import VectorField

from common.choices import EventStatusChoices, RegistrationStatusChoices


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text='CSS icon class name')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_events')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='events')
    date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=300)
    address = models.TextField(blank=True)
    image = models.ImageField(upload_to='events/', blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_participants = models.PositiveIntegerField(default=100)
    status = models.CharField(max_length=20, choices=EventStatusChoices.choices, default=EventStatusChoices.PENDING)
    is_online = models.BooleanField(default=False)
    online_link = models.URLField(blank=True)

    # Tax & service-fee configuration (percentages of the subtotal).
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                      help_text='e.g. 12 for 12% VAT')
    service_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                              help_text='Platform/booking fee as a %')
    # True  → fees added on top, buyer pays them.
    # False → fees absorbed, included in the displayed price.
    fees_passed_to_buyer = models.BooleanField(default=True)
    currency = models.CharField(max_length=3, default='USD')

    # When False, paid tickets cannot be refunded — attendees see a
    # "non-refundable" notice instead of a refund button.
    refundable = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 384-dim MiniLM embedding for semantic search (null until generated)
    embedding = VectorField(dimensions=384, null=True, blank=True)

    # SEO overrides — leave blank to auto-derive from title/description/image
    seo_title = models.CharField(max_length=200, blank=True, help_text='Custom <title> / og:title (falls back to event title)')
    seo_description = models.CharField(max_length=500, blank=True, help_text='Custom meta description / og:description')

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return self.title

    @property
    def available_spots(self):
        registered = self.registrations.exclude(status__in=[
            RegistrationStatusChoices.CANCELLED,
            RegistrationStatusChoices.REJECTED,
        ]).count()
        # Group bookings hold seats without Registration rows — count their
        # seats too so capacity reflects every kind of sale.
        try:
            from bookings.models import BookingSeat, Booking
            booked = BookingSeat.objects.filter(
                booking__event=self,
                booking__status__in=[Booking.Status.HOLDING, Booking.Status.CONFIRMED],
            ).count()
        except Exception:
            booked = 0
        return max(self.max_participants - registered - booked, 0)

    @property
    def has_ticket_types(self):
        return self.ticket_types.exists()

    @property
    def is_free(self):
        # With ticket tiers, the event is free only if every tier is free.
        if self.has_ticket_types:
            return not self.ticket_types.exclude(kind=TicketType.KIND_FREE).exists()
        return self.price == 0

    @property
    def price_from(self):
        """Lowest purchasable price across tiers (for 'from $X' display)."""
        if not self.has_ticket_types:
            return self.price
        prices = [t.price for t in self.ticket_types.filter(is_active=True)]
        return min(prices) if prices else self.price

    @property
    def check_in_count(self):
        return self.registrations.filter(is_checked_in=True).count()


class SeatMap(models.Model):
    """Схема посадочных мест для события."""
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name='seat_map')
    rows = models.PositiveIntegerField(default=6)
    cols = models.PositiveIntegerField(default=7)
    layout = models.JSONField(default=dict, blank=True, help_text='Metadata: {"price_zones": {"vip": [rows], "standard": [rows]}}')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'seat maps'

    def __str__(self):
        return f'SeatMap for {self.event.title}'


class EventSeat(models.Model):
    """Индивидуальное место на схеме."""
    PRICE_ZONE_CHOICES = [('standard', 'Standard'), ('vip', 'VIP'), ('premium', 'Premium')]

    seat_map = models.ForeignKey(SeatMap, on_delete=models.CASCADE, related_name='seats')
    row = models.PositiveIntegerField()
    col = models.PositiveIntegerField()
    price_zone = models.CharField(max_length=20, choices=PRICE_ZONE_CHOICES, default='standard')
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ('seat_map', 'row', 'col')
        indexes = [models.Index(fields=['seat_map', 'is_available'])]

    def __str__(self):
        return f'Seat {self.row}-{self.col} ({self.price_zone})'


class Registration(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='registrations')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    status = models.CharField(max_length=20, choices=RegistrationStatusChoices.choices, default=RegistrationStatusChoices.PENDING)
    registered_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    # New fields for QR Tickets
    ticket_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    is_checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    # New field for seat selection
    seat = models.ForeignKey(EventSeat, on_delete=models.SET_NULL, null=True, blank=True, related_name='registrations')
    # Until when an unpaid seat/spot is held before being auto-released.
    seat_held_until = models.DateTimeField(null=True, blank=True)

    # Promo code applied at checkout (nullable). The discounted amount lives on
    # the Payment row; this just records which code was used.
    promo_code = models.ForeignKey(
        'PromoCode', on_delete=models.SET_NULL, null=True, blank=True, related_name='registrations'
    )

    # Ticket tier chosen at checkout (nullable for legacy single-price events).
    ticket_type = models.ForeignKey(
        'TicketType', on_delete=models.SET_NULL, null=True, blank=True, related_name='registrations'
    )
    # For donation tiers: the amount the attendee chose to pay (>= min price).
    donation_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Price locked at registration time for flat-priced (GA) events, so the
    # dynamic-pricing engine can't change the amount between the quote the
    # attendee saw and what Stripe charges.
    locked_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Promoter whose referral link brought this attendee (nullable).
    affiliate = models.ForeignKey(
        'Affiliate', on_delete=models.SET_NULL, null=True, blank=True, related_name='registrations'
    )

    class Meta:
        unique_together = ('user', 'event')
        ordering = ['-registered_at']

    def __str__(self):
        return f'{self.user.username} -> {self.event.title}'


class TicketType(models.Model):
    """A purchasable tier for an event: General, VIP, Early Bird, Donation…

    Ticket types are optional. An event with no ticket types keeps using the
    single Event.price flow (and seat maps). When an event HAS ticket types,
    attendees pick one tier at checkout and its price/capacity rules apply.
    """
    KIND_PAID = 'paid'
    KIND_FREE = 'free'
    KIND_DONATION = 'donation'
    KIND_CHOICES = [
        (KIND_PAID, 'Paid'),
        (KIND_FREE, 'Free'),
        (KIND_DONATION, 'Donation (pay what you want)'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticket_types')
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_PAID)
    # For paid: the price. For donation: the minimum / suggested amount. Free: 0.
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Capacity for THIS tier (null = unlimited, bounded only by event capacity).
    quantity = models.PositiveIntegerField(null=True, blank=True)
    min_per_order = models.PositiveIntegerField(default=1)
    max_per_order = models.PositiveIntegerField(default=10)
    # Optional sale window.
    sale_start = models.DateTimeField(null=True, blank=True)
    sale_end = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'price', 'id']

    def __str__(self):
        return f'{self.name} — {self.event.title}'

    @property
    def sold(self):
        return self.registrations.exclude(status__in=[
            RegistrationStatusChoices.CANCELLED,
            RegistrationStatusChoices.REJECTED,
        ]).count()

    @property
    def available(self):
        if self.quantity is None:
            return None  # unlimited
        return max(self.quantity - self.sold, 0)

    @property
    def is_sold_out(self):
        return self.quantity is not None and self.sold >= self.quantity

    @property
    def on_sale(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.sale_start and now < self.sale_start:
            return False
        if self.sale_end and now > self.sale_end:
            return False
        return True

    @property
    def sale_state(self):
        """Human label for why a tier can/can't be bought right now."""
        now = timezone.now()
        if not self.is_active:
            return 'inactive'
        if self.sale_start and now < self.sale_start:
            return 'scheduled'
        if self.sale_end and now > self.sale_end:
            return 'ended'
        if self.is_sold_out:
            return 'sold_out'
        return 'on_sale'


class PromoCode(models.Model):
    """Discount code an organizer creates for an event.

    Supports percentage or fixed-amount discounts, optional usage cap and
    expiry. Validation lives in events.promo so the rules stay in one place.
    """
    DISCOUNT_PERCENT = 'percent'
    DISCOUNT_FIXED = 'fixed'
    DISCOUNT_TYPES = [
        (DISCOUNT_PERCENT, 'Percentage'),
        (DISCOUNT_FIXED, 'Fixed amount'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='promo_codes')
    code = models.CharField(max_length=50, help_text='Case-insensitive code attendees type at checkout')
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default=DISCOUNT_PERCENT)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, help_text='20 = 20% (percent) or $20 (fixed)')
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text='Blank = unlimited')
    times_used = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'code')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code} ({self.event.title})'

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() > self.expires_at)

    @property
    def is_exhausted(self):
        return self.max_uses is not None and self.times_used >= self.max_uses

    @property
    def is_valid(self):
        return self.is_active and not self.is_expired and not self.is_exhausted


class EventQuestion(models.Model):
    """A custom question an organizer asks attendees during checkout.

    Answers are stored per-registration in QuestionAnswer. Types mirror common
    form controls so the frontend can render the right input.
    """
    TYPE_TEXT = 'text'
    TYPE_TEXTAREA = 'textarea'
    TYPE_DROPDOWN = 'dropdown'
    TYPE_CHECKBOX = 'checkbox'
    TYPE_DATE = 'date'
    TYPE_PHONE = 'phone'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Short text'),
        (TYPE_TEXTAREA, 'Long text'),
        (TYPE_DROPDOWN, 'Dropdown'),
        (TYPE_CHECKBOX, 'Checkbox'),
        (TYPE_DATE, 'Date'),
        (TYPE_PHONE, 'Phone'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='questions')
    label = models.CharField(max_length=255)
    question_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_TEXT)
    options = models.JSONField(default=list, blank=True, help_text='Choices for dropdown type')
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.label} ({self.event.title})'


class QuestionAnswer(models.Model):
    """An attendee's answer to one EventQuestion for their registration."""
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(EventQuestion, on_delete=models.CASCADE, related_name='answers')
    answer = models.TextField(blank=True)

    class Meta:
        unique_together = ('registration', 'question')

    def __str__(self):
        return f'{self.question.label}: {self.answer[:30]}'


class WaitlistEntry(models.Model):
    """A user waiting for a sold-out event. FIFO; auto-offered on free spot."""
    STATUS_WAITING = 'waiting'
    STATUS_OFFERED = 'offered'
    STATUS_CONVERTED = 'converted'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_WAITING, 'Waiting'),
        (STATUS_OFFERED, 'Offered'),
        (STATUS_CONVERTED, 'Converted'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='waitlist_entries')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='waitlist')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_WAITING)
    # When an offer was sent and until when it's valid before passing to the next.
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'event')
        ordering = ['created_at']  # FIFO
        verbose_name_plural = 'waitlist entries'

    def __str__(self):
        return f'{self.user.username} waiting for {self.event.title} ({self.status})'


class RefundRequest(models.Model):
    """An attendee's request to refund their paid ticket.

    Created by the attendee, then approved or rejected by the organizer.
    - Approved → the payment is refunded and the registration cancelled.
    - Rejected → the registration is marked rejected.
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    registration = models.OneToOneField(Registration, on_delete=models.CASCADE, related_name='refund_request')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reason = models.TextField(blank=True, help_text="Attendee's reason for the request")
    organizer_note = models.CharField(max_length=300, blank=True, help_text="Organizer's response")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Refund {self.status} — {self.registration.user.username} / {self.registration.event.title}'


class Favorite(models.Model):
    """User saves an event to favourites."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'event')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} ♥ {self.event.title}'


class Review(models.Model):
    """Star rating + comment left by an attendee after the event."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])  # 1-5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'event')  # one review per user per event
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} → {self.event.title} ({self.rating}★)'


class EventStaff(models.Model):
    """A team member with a role on a specific event.

    Lets an organizer delegate: a co-organizer can do everything they can on
    that event; check-in staff can only scan tickets. The organizer themselves
    is never an EventStaff row — they're the owner via Event.organizer.
    """
    ROLE_CO_ORGANIZER = 'co_organizer'
    ROLE_CHECK_IN = 'check_in'
    ROLE_CHOICES = [
        (ROLE_CO_ORGANIZER, 'Co-organizer (full access)'),
        (ROLE_CHECK_IN, 'Check-in staff (scan only)'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='staff')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='event_roles')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CHECK_IN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'user')
        verbose_name_plural = 'event staff'

    def __str__(self):
        return f'{self.user.username} — {self.role} @ {self.event.title}'


class Webhook(models.Model):
    """An outbound webhook an organizer registers for an event.

    On each subscribed trigger we POST a JSON payload signed with `secret`
    (HMAC-SHA256 in the X-EventHub-Signature header) so the receiver can verify
    authenticity. Deliveries are logged for debugging.
    """
    TRIGGER_TICKET_SOLD = 'ticket_sold'
    TRIGGER_REGISTRATION = 'registration_created'
    TRIGGER_REFUND = 'refund_issued'
    TRIGGER_CHECK_IN = 'attendee_checked_in'
    TRIGGER_CHOICES = [
        (TRIGGER_TICKET_SOLD, 'Ticket sold (paid)'),
        (TRIGGER_REGISTRATION, 'Registration created'),
        (TRIGGER_REFUND, 'Refund issued'),
        (TRIGGER_CHECK_IN, 'Attendee checked in'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='webhooks')
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=64, blank=True, help_text='Used to sign payloads')
    triggers = models.JSONField(default=list, help_text='List of trigger keys this webhook fires on')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    last_status = models.IntegerField(null=True, blank=True, help_text='HTTP status of the last delivery')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Webhook → {self.url} ({self.event.title})'


class WebhookDelivery(models.Model):
    """Log of one webhook POST attempt (for debugging in the UI)."""
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name='deliveries')
    trigger = models.CharField(max_length=30)
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Affiliate(models.Model):
    """A promoter with a tracked referral link for an event.

    Attendees who arrive via ?ref=<code> get the code stored on their
    registration, so the organizer can attribute clicks, sales and revenue to
    each promoter.
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='affiliates')
    name = models.CharField(max_length=120, help_text='Promoter name / channel')
    code = models.CharField(max_length=40, help_text='Goes in the ?ref= link')
    clicks = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'code')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.code}) @ {self.event.title}'

    @property
    def sales(self):
        return self.registrations.exclude(status__in=[
            RegistrationStatusChoices.CANCELLED, RegistrationStatusChoices.REJECTED,
        ]).count()


class CheckInList(models.Model):
    """A named check-in gate for an event (e.g. 'General Entrance', 'VIP Door').

    An event can have multiple lists so staff at different entrances each scan
    into the correct gate. Every check-in action is recorded in CheckInLog.
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='checkin_lists')
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    color = models.CharField(max_length=7, default='#4f46e5', help_text='Hex color for UI badge')
    is_default = models.BooleanField(default=False, help_text='The list used by the QR scanner when no list is selected')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'check-in list'
        verbose_name_plural = 'check-in lists'

    def __str__(self):
        return f'{self.name} @ {self.event.title}'


class CheckInLog(models.Model):
    """Audit log of every check-in action (and undo) across all lists."""
    ACTION_CHECK_IN = 'check_in'
    ACTION_UNDO = 'undo'
    ACTION_CHOICES = [
        (ACTION_CHECK_IN, 'Checked in'),
        (ACTION_UNDO, 'Undo check-in'),
    ]

    checkin_list = models.ForeignKey(CheckInList, on_delete=models.CASCADE, related_name='logs')
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='checkin_logs')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, default=ACTION_CHECK_IN)
    scanned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='checkin_actions')
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'check-in log entry'
        verbose_name_plural = 'check-in log entries'

    def __str__(self):
        return f'{self.action} — {self.registration} via {self.checkin_list.name}'


class Notification(models.Model):
    """In-app notifications for users."""
    TYPE_CHOICES = [
        ('ticket_purchased', '🎫 Ticket purchased'),
        ('event_reminder',   '⏰ Event reminder'),
        ('seat_available',   '💺 Seat available'),
        ('event_updated',    '📝 Event updated'),
        ('event_cancelled',  '❌ Event cancelled'),
        ('payment_failed',   '⚠️ Payment failed'),
        ('review_reminder',  '⭐ Leave a review'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.type}] → {self.user.username}'
