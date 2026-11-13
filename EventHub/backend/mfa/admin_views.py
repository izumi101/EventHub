"""/admin/mfa/verify/: the second step of the Django admin login."""

import time

from django import forms
from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .exceptions import MFAError
from .middleware import mark_admin_session_verified
from .models import EmailCode
from .policy import (
    METHOD_EMAIL,
    METHOD_RECOVERY,
    METHOD_TOTP,
    has_totp,
    has_usable_email,
    mfa_enabled,
    mfa_required_for,
)
from .services import send_email_code, verify_second_factor


class AdminVerifyForm(forms.Form):
    method = forms.ChoiceField(
        choices=[(METHOD_TOTP, 'Authenticator app code'), (METHOD_RECOVERY, 'Recovery code')],
        initial=METHOD_TOTP,
        widget=forms.RadioSelect,
    )
    code = forms.CharField(
        max_length=32,
        widget=forms.TextInput(attrs={'autocomplete': 'one-time-code', 'autofocus': True, 'inputmode': 'text'}),
    )

    def __init__(self, *args, email=False, **kwargs):
        super().__init__(*args, **kwargs)
        if email:
            self.fields['method'].choices = [*self.fields['method'].choices, (METHOD_EMAIL, 'Code sent by email')]


def _safe_next(request) -> str:
    target = request.POST.get('next') or request.GET.get('next') or reverse('admin:index')
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return reverse('admin:index')


@never_cache
@csrf_protect
def admin_verify(request):
    user = request.user
    if not user.is_authenticated or not user.is_staff:
        return redirect_to_login(request.get_full_path(), reverse('admin:login'))
    next_url = _safe_next(request)
    context = {
        **admin.site.each_context(request),
        'title': 'Two-factor authentication',
        'next': next_url,
        'needs_enrollment': not mfa_enabled(user) and mfa_required_for(user),
        'has_totp': has_totp(user),
        'has_email': has_usable_email(user),
    }
    if context['needs_enrollment']:
        return render(request, 'mfa/admin_verify.html', context, status=403)

    if request.method == 'POST' and 'send_email_code' in request.POST and context['has_email']:
        try:
            send_email_code(user, EmailCode.PURPOSE_STEP_UP, request=request)
            context['email_notice'] = 'We sent a code to your email address. It expires in 10 minutes.'
        except MFAError as exc:
            context['email_notice'] = str(exc.detail)
        context['form'] = AdminVerifyForm(initial={'method': METHOD_EMAIL}, email=True)
        return render(request, 'mfa/admin_verify.html', context)

    form = AdminVerifyForm(request.POST or None, email=context['has_email'])
    if request.method == 'POST' and form.is_valid():
        try:
            verify_second_factor(
                user,
                method=form.cleaned_data['method'],
                code=form.cleaned_data['code'],
                request=request,
                context='admin',
            )
        except MFAError as exc:
            form.add_error('code', str(exc.detail))
        else:
            mark_admin_session_verified(request, int(time.time()))
            return redirect(next_url)
    context['form'] = form
    return render(request, 'mfa/admin_verify.html', context)
