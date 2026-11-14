"""Opting in / out, factor management, lockout and throttling, the Django
admin's second step and the mfa_reset command."""

from datetime import timedelta
from io import StringIO

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken

from events.models import Notification
from jobs.models import Job

from .models import MFAState, RecoveryCode, TOTPDevice
from .test_login import PROFILE, MFABase
from .testing import authenticate_with_recent_mfa, enroll_totp, mark_admin_session_verified, totp_code


class AttendeeOptInTests(MFABase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user('ann')
        self.tokens = self.login(self.user).data['tokens']
        self.bearer(self.tokens['access'])

    def enable(self):
        secret = self.client.post('/api/v1/auth/mfa/totp/setup/').data['secret']
        response = self.client.post('/api/v1/auth/mfa/totp/confirm/', {'code': totp_code(secret)})
        self.assertEqual(response.status_code, 200, response.data)
        return secret, response

    def test_enabling_2fa_signs_out_other_sessions_and_notifies(self):
        _, response = self.enable()
        self.assertEqual(len(response.data['recovery_codes']), 10)
        # Old refresh token (password only) is dead; the new pair works.
        self.client.credentials()
        self.assertEqual(
            self.client.post('/api/v1/auth/token/refresh/', {'refresh': self.tokens['refresh']}).status_code, 401
        )
        self.bearer(response.data['tokens']['access'])
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        self.assertTrue(
            Notification.objects.filter(user=self.user, type='security_alert', title__icontains='is on').exists()
        )
        self.assertTrue(Job.objects.filter(kind='send_email', payload__to=[self.user.email]).exists())

    def test_setup_while_active_is_refused(self):
        self.enable()
        authenticate_with_recent_mfa(self.client, self.user)
        response = self.client.post('/api/v1/auth/mfa/totp/setup/')
        self.assertEqual(response.status_code, 409)

    def test_disabling_needs_step_up_and_notifies(self):
        self.enable()
        authenticate_with_recent_mfa(self.client, self.user, age_seconds=3600)
        self.assertEqual(self.client.post('/api/v1/auth/mfa/disable/').status_code, 403)
        authenticate_with_recent_mfa(self.client, self.user)
        response = self.client.post('/api/v1/auth/mfa/disable/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['enabled'])
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(RecoveryCode.objects.filter(user=self.user).exists())
        self.assertTrue(Notification.objects.filter(user=self.user, title__icontains='is off').exists())
        self.client.force_authenticate(None)
        self.client.credentials()
        self.assertIn('tokens', self.login(self.user).data)

    def test_regenerating_codes_needs_step_up(self):
        self.enable()
        authenticate_with_recent_mfa(self.client, self.user, age_seconds=3600)
        self.assertEqual(self.client.post('/api/v1/auth/mfa/recovery-codes/regenerate/').status_code, 403)
        authenticate_with_recent_mfa(self.client, self.user)
        response = self.client.post('/api/v1/auth/mfa/recovery-codes/regenerate/')
        self.assertEqual(len(response.data['recovery_codes']), 10)


class OrganizerCannotDisableTests(MFABase):
    def test_required_users_keep_their_last_factor(self):
        organizer = self.make_user('org', role='organizer')
        enroll_totp(organizer)
        authenticate_with_recent_mfa(self.client, organizer)
        for method, url in (('post', '/api/v1/auth/mfa/disable/'), ('delete', '/api/v1/auth/mfa/totp/')):
            response = getattr(self.client, method)(url)
            self.assertEqual((response.status_code, response.data['code']), (409, 'mfa_required_by_policy'))
        self.assertTrue(TOTPDevice.objects.filter(user=organizer, confirmed=True).exists())


class LockoutAndThrottleTests(MFABase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user('olga', role='organizer')
        self.secret = enroll_totp(self.user)
        authenticate_with_recent_mfa(self.client, self.user, age_seconds=3600)

    def step_up(self, code):
        return self.client.post('/api/v1/auth/mfa/step-up/', {'method': 'totp', 'code': code})

    def test_five_wrong_codes_lock_the_second_factor(self):
        wrong = '000000' if totp_code(self.secret) != '000000' else '111111'
        for _ in range(4):
            self.assertEqual(self.step_up(wrong).status_code, 400)
        locked = self.step_up(wrong)
        self.assertEqual((locked.status_code, locked.data['code']), (429, 'mfa_locked'))
        self.assertEqual(locked['Retry-After'], '60')
        # The right code is refused while locked.
        self.assertEqual(self.step_up(totp_code(self.secret)).status_code, 429)
        # After the lock: the right code works and resets the counter.
        MFAState.objects.filter(user=self.user).update(locked_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.step_up(totp_code(self.secret)).status_code, 200)
        self.assertEqual(MFAState.objects.get(user=self.user).failed_attempts, 0)

    def test_the_lock_doubles_with_further_failures(self):
        MFAState.objects.create(user=self.user, failed_attempts=5)
        response = self.step_up('000000' if totp_code(self.secret) != '000000' else '111111')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data['retry_after'], 120)

    def test_the_lockout_also_covers_login(self):
        MFAState.objects.create(user=self.user, locked_until=timezone.now() + timedelta(minutes=5))
        self.client.force_authenticate(None)
        challenge = self.login(self.user).data['challenge_token']
        response = self.client.post(
            '/api/v1/auth/mfa/login/verify/',
            {'challenge_token': challenge, 'method': 'totp', 'code': totp_code(self.secret)},
        )
        self.assertEqual(response.status_code, 429)

    @override_settings(MFA_THROTTLE_RATES={'mfa_user': '2/min'})
    def test_per_user_throttle(self):
        cache.clear()
        self.step_up('000001')
        self.step_up('000002')
        self.assertEqual(self.step_up('000003').status_code, 429)

    @override_settings(MFA_THROTTLE_RATES={'mfa_ip': '2/min'})
    def test_per_ip_throttle_on_the_login_step(self):
        cache.clear()
        self.client.force_authenticate(None)
        url = '/api/v1/auth/mfa/login/verify/'
        statuses = [
            self.client.post(url, {'challenge_token': 'x', 'method': 'totp', 'code': '1'}).status_code for _ in range(3)
        ]
        self.assertEqual(statuses[-1], 429)


class AdminSecondFactorTests(MFABase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_user('root', is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)

    def test_the_admin_asks_for_the_second_factor(self):
        secret = enroll_totp(self.admin)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/admin/mfa/verify/'))
        page = self.client.get(response['Location'])
        self.assertContains(page, 'one-time-code')
        wrong = self.client.post(
            '/admin/mfa/verify/?next=/admin/', {'method': 'totp', 'code': '000000', 'next': '/admin/'}
        )
        self.assertEqual(wrong.status_code, 200)
        ok = self.client.post('/admin/mfa/verify/', {'method': 'totp', 'code': totp_code(secret), 'next': '/admin/'})
        self.assertRedirects(ok, '/admin/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_a_staff_member_without_2fa_cannot_use_the_admin(self):
        self.assertEqual(self.client.get('/admin/payments/payment/').status_code, 302)
        page = self.client.get('/admin/mfa/verify/')
        self.assertEqual(page.status_code, 403)
        self.assertContains(page, 'Profile → Security', status_code=403)

    def test_an_offsite_next_url_is_ignored(self):
        secret = enroll_totp(self.admin)
        response = self.client.post(
            '/admin/mfa/verify/', {'method': 'totp', 'code': totp_code(secret), 'next': 'https://evil.example/'}
        )
        self.assertRedirects(response, '/admin/', fetch_redirect_response=False)

    def test_the_proof_belongs_to_the_user(self):
        other = self.make_user('other_admin', is_staff=True)
        enroll_totp(self.admin)
        mark_admin_session_verified(self.client, other)
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    @override_settings(MFA_REQUIRED_ROLES=[])
    def test_with_enforcement_off_staff_without_2fa_get_in(self):
        self.assertEqual(self.client.get('/admin/').status_code, 200)


class ResetCommandTests(MFABase):
    def test_the_confirmation_flag_is_required(self):
        user = self.make_user('olga', role='organizer')
        enroll_totp(user)
        with self.assertRaises(CommandError):
            call_command('mfa_reset', 'olga')
        self.assertTrue(TOTPDevice.objects.filter(user=user).exists())

    def test_reset_removes_factors_signs_out_and_logs(self):
        user = self.make_user('olga', role='organizer')
        enroll_totp(user)
        from . import recovery

        recovery.regenerate(user)
        MFAState.objects.create(user=user, failed_attempts=7, locked_until=timezone.now() + timedelta(hours=1))
        refresh = self.client.post('/api/v1/auth/login/', {'username': 'olga', 'password': self.password})
        self.assertTrue(refresh.data['mfa_required'])
        from rest_framework_simplejwt.tokens import RefreshToken

        RefreshToken.for_user(user)  # an open session
        out = StringIO()
        with self.assertLogs('mfa', level='WARNING') as logs:
            call_command(
                'mfa_reset', 'olga', '--yes-i-verified-the-user', '--operator', 'alice', '--reason', 'T-42', stdout=out
            )
        self.assertIn('2FA reset for olga', out.getvalue())
        self.assertIn('mfa.admin_reset', '\n'.join(logs.output))
        self.assertIn('alice (T-42)', '\n'.join(logs.output))
        self.assertFalse(TOTPDevice.objects.filter(user=user).exists())
        self.assertFalse(RecoveryCode.objects.filter(user=user).exists())
        state = MFAState.objects.get(user=user)
        self.assertEqual((state.failed_attempts, state.locked_until), (0, None))
        outstanding = OutstandingToken.objects.filter(user=user).count()
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), outstanding)
        self.assertTrue(Notification.objects.filter(user=user, title__icontains='reset').exists())
        # Policy still applies: the organizer enrolls again at the next sign-in.
        self.assertTrue(self.login(user).data['mfa_enrollment_required'])

    def test_unknown_user(self):
        with self.assertRaises(CommandError):
            call_command('mfa_reset', 'nobody', '--yes-i-verified-the-user')


class TokenShapeTests(MFABase):
    def test_access_tokens_from_a_second_factor_login_cannot_be_forged_from_a_password_token(self):
        # A password-only token can't be turned into a 2FA token without the
        # signing key (sanity check of the claim being inside the signature).
        user = self.make_user('ann')
        token = AccessToken(self.login(user).data['tokens']['access'])
        header, payload, signature = str(token).split('.')
        self.bearer(f'{header}.{payload}x.{signature}')
        self.assertEqual(self.client.get(PROFILE).status_code, 401)
