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

