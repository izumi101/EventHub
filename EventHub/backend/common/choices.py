from django.db import models


class RoleChoices(models.TextChoices):
    ATTENDEE = 'attendee', 'Attendee'
    ORGANIZER = 'organizer', 'Organizer'


class EventStatusChoices(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING = 'pending', 'Pending Approval'
    PUBLISHED = 'published', 'Published'
    CANCELLED = 'cancelled', 'Cancelled'
    COMPLETED = 'completed', 'Completed'
    REJECTED = 'rejected', 'Rejected'


class RegistrationStatusChoices(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    CANCELLED = 'cancelled', 'Cancelled'
    REJECTED = 'rejected', 'Rejected'


class PaymentStatusChoices(models.TextChoices):
    PENDING = 'pending', 'Pending'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    REFUNDED = 'refunded', 'Refunded'


class PaymentProviderChoices(models.TextChoices):
    """Who moved (or will move) the money of a payment (ADR 0001)."""

    STRIPE = 'stripe', 'Stripe'
    FREEDOMPAY = 'freedompay', 'Freedom Pay'
    MOCK = 'mock', 'Mock (development only)'
    OFFLINE = 'offline', 'Offline / manual'


class PaymentCallbackKind(models.TextChoices):
    """Provider callbacks normalised to what they mean for a payment."""

    PAID = 'paid', 'Paid'
    FAILED = 'failed', 'Failed'
    EXPIRED = 'expired', 'Expired'
    REFUNDED = 'refunded', 'Refunded'
    DISPUTE_OPENED = 'dispute_opened', 'Dispute opened'
    DISPUTE_WON = 'dispute_won', 'Dispute won'
    DISPUTE_LOST = 'dispute_lost', 'Dispute lost'
    IGNORED = 'ignored', 'Ignored'
