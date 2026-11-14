"""Step-up (re-verification) for sensitive actions.

A sensitive view calls `require_recent_mfa(request)` once it knows the user
may perform the action. It passes when the access token's `mfa_at` is at most
MFA_STEP_UP_MAX_AGE_SECONDS old; otherwise the API answers 403
`mfa_step_up_required` and the SPA asks for a factor
(POST /auth/mfa/step-up/), then retries.
"""

import time

from django.conf import settings

from .exceptions import EnrollmentRequired, StepUpRequired
from .policy import available_methods, mfa_enabled, mfa_required_for, token_mfa_at


def step_up_max_age() -> int:
    return int(settings.MFA_STEP_UP_MAX_AGE_SECONDS)


def has_recent_mfa(request) -> bool:
    mfa_at = token_mfa_at(getattr(request, 'auth', None))
    if mfa_at is None:
        return False
    age = int(time.time()) - mfa_at
    return -60 <= age <= step_up_max_age()  # small negative: clock skew between workers


def step_up_valid_until(request) -> int | None:
    mfa_at = token_mfa_at(getattr(request, 'auth', None))
    return None if mfa_at is None else mfa_at + step_up_max_age()


def require_recent_mfa(request, *, allow_without_mfa: bool = False) -> None:
    """Raise unless the request carries a fresh second-factor proof.

    allow_without_mfa=True lets a user who neither has nor needs 2FA through
    (e.g. an attendee changing their password); otherwise such a user is told
    to set up 2FA first — money and personal-data actions always need it.
    """
    if has_recent_mfa(request):
        return
    user = request.user
    if not mfa_enabled(user):
        if allow_without_mfa and not mfa_required_for(user):
            return
        raise EnrollmentRequired()
    raise StepUpRequired(
        extra={'methods': available_methods(user), 'max_age': step_up_max_age()},
    )
