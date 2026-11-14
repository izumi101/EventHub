"""Second factor for the Django admin.

Django's admin login checks the password only. This middleware sends every
authenticated staff session under /admin/ that has not passed a second
factor to /admin/mfa/verify/ (mfa/admin_views.py). The proof is stored in
the session together with the user id; Django rotates the session key at
login and flushes it at logout.
"""

from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from django.urls import reverse

SESSION_USER = 'mfa_admin_user_id'
SESSION_AT = 'mfa_admin_verified_at'


def admin_session_verified(request) -> bool:
    return request.session.get(SESSION_USER) == request.user.pk and bool(request.session.get(SESSION_AT))


def mark_admin_session_verified(request, when: int) -> None:
    request.session.cycle_key()
    request.session[SESSION_USER] = request.user.pk
    request.session[SESSION_AT] = when


class AdminMFAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redirect = self._check(request)
        return redirect or self.get_response(request)

    def _check(self, request):
        admin_root = reverse('admin:index')
        if not request.path.startswith(admin_root):
            return None
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated or not user.is_staff:
            return None  # the admin's own login page handles these
        verify_url = reverse('admin_mfa_verify')
        exempt = (verify_url, reverse('admin:logout'), reverse('admin:jsi18n'))
        if request.path in exempt or admin_session_verified(request):
            return None
        from .policy import mfa_enabled, mfa_required_for

        if not mfa_enabled(user) and not mfa_required_for(user):
            return None  # policy off for this user and no factor to ask for
        return HttpResponseRedirect(f'{verify_url}?{urlencode({"next": request.get_full_path()})}')
