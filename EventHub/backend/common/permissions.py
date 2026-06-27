from django.contrib.auth.models import User

from events.models import Event, Registration, EventStaff


def is_event_organizer(event: Event, user: User) -> bool:
    return event.organizer_id == user.id


def _staff_role(event: Event, user: User):
    if not user or not user.is_authenticated:
        return None
    row = EventStaff.objects.filter(event=event, user=user).only('role').first()
    return row.role if row else None


def can_manage_event(event: Event, user: User) -> bool:
    """Full management: owner, superuser, or a co-organizer team member."""
    if user.is_superuser or is_event_organizer(event, user):
        return True
    return _staff_role(event, user) == EventStaff.ROLE_CO_ORGANIZER


def can_check_in_event(event: Event, user: User) -> bool:
    """Scan/check-in rights: anyone who can manage, plus check-in staff."""
    if can_manage_event(event, user):
        return True
    return _staff_role(event, user) == EventStaff.ROLE_CHECK_IN


def can_manage_registration(registration: Registration, user: User) -> bool:
    return can_manage_event(registration.event, user)
