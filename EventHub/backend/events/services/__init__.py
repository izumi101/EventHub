"""Domain services for the events app, split by concern.

Always import from ``events.services`` — the submodule layout is an
internal detail and may change:

- ``realtime``     — WebSocket broadcasts
- ``holds``        — seat-hold expiry / paid-registration reconciliation
- ``lifecycle``    — event create/update/clone and status transitions
- ``registration`` — ticket purchase, cancellation, check-in
- ``refunds``      — refund requests and resolution
"""

from .realtime import broadcast_seat_update
from .holds import (
    SEAT_HOLD_MINUTES,
    release_expired_seat_holds,
    reconcile_paid_registrations,
)
from .lifecycle import (
    approve_event,
    cancel_event,
    clone_event,
    create_event,
    mark_completed_if_past,
    reject_event,
    submit_event,
    update_event,
)
from .registration import (
    attendee_cancel,
    cancel_registration,
    check_in_registration,
    ensure_attendee_can_buy,
    register_for_event,
)
from .refunds import (
    request_refund,
    resolve_refund_request,
)

__all__ = [
    'broadcast_seat_update',
    'SEAT_HOLD_MINUTES',
    'release_expired_seat_holds',
    'reconcile_paid_registrations',
    'approve_event',
    'cancel_event',
    'clone_event',
    'create_event',
    'mark_completed_if_past',
    'reject_event',
    'submit_event',
    'update_event',
    'attendee_cancel',
    'cancel_registration',
    'check_in_registration',
    'ensure_attendee_can_buy',
    'register_for_event',
    'request_refund',
    'resolve_refund_request',
]
