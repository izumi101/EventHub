"""Domain services for the events app, split by concern.

Always import from ``events.services`` — the submodule layout is an
internal detail and may change:

- ``realtime``     — WebSocket broadcasts
- ``holds``        — seat-hold expiry / paid-registration reconciliation
- ``lifecycle``    — event create/update/clone and status transitions
- ``registration`` — ticket purchase, cancellation, check-in
- ``refunds``      — refund requests and resolution
"""

from .holds import (
    SEAT_HOLD_MINUTES,
    reconcile_paid_registrations,
    release_expired_seat_holds,
)
from .lifecycle import (
    approve_event,
    cancel_event,
    clone_event,
    create_event,
    reject_event,
    submit_event,
    update_event,
)
from .realtime import broadcast_seat_update
from .refunds import (
    request_refund,
    resolve_refund_request,
)
from .registration import (
    attendee_cancel,
    cancel_registration,
    check_in_registration,
    ensure_attendee_can_buy,
    ensure_event_on_sale,
    get_active_registration,
    register_for_event,
)

__all__ = [
    'SEAT_HOLD_MINUTES',
    'approve_event',
    'attendee_cancel',
    'broadcast_seat_update',
    'cancel_event',
    'cancel_registration',
    'check_in_registration',
    'clone_event',
    'create_event',
    'ensure_attendee_can_buy',
    'ensure_event_on_sale',
    'get_active_registration',
    'reconcile_paid_registrations',
    'register_for_event',
    'reject_event',
    'release_expired_seat_holds',
    'request_refund',
    'resolve_refund_request',
    'submit_event',
    'update_event',
]
