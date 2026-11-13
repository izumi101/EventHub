"""Login with a second factor, enforcement for organizers/staff, the
single-purpose challenge and enrollment tokens, and refresh vs. mfa_at."""

import time
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from events.models import Notification
from jobs.models import Job

from . import recovery
from .models import TOTPDevice
from .testing import enroll_totp, totp_code
from .tokens import MFAChallengeToken, MFAEnrollmentToken

LOGIN = '/api/v1/auth/login/'
VERIFY = '/api/v1/auth/mfa/login/verify/'
PROFILE = '/api/v1/auth/profile/'
REFRESH = '/api/v1/auth/token/refresh/'


class MFABase(APITestCase):
    password = 'Str0ng-pass!'

    def setUp(self):
        cache.clear()

    def make_user(self, name, role='attendee', **flags):
        user = User.objects.create_user(name, f'{name}@example.com', self.password, **flags)
        user.profile.role = role
        user.profile.save()
        return user

    def login(self, user):
        return self.client.post(LOGIN, {'username': user.username, 'password': self.password})

    def bearer(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class PasswordOnlyLoginTests(MFABase):
    def test_an_attendee_without_2fa_gets_tokens_without_a_second_factor_claim(self):
        response = self.login(self.make_user('ann'))
        self.assertEqual(response.status_code, 200)
        access = AccessToken(response.data['tokens']['access'])
        self.assertEqual(access['amr'], ['pwd'])
        self.assertNotIn('mfa_at', access.payload)

    def test_wrong_password_reveals_nothing_about_2fa(self):
        user = self.make_user('ann')
        enroll_totp(user)
        response = self.client.post(LOGIN, {'username': 'ann', 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('challenge_token', response.data)


class SecondFactorLoginTests(MFABase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user('olga', role='organizer')
        self.secret = enroll_totp(self.user)

    def challenge(self):
        response = self.login(self.user)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['mfa_required'])
        self.assertNotIn('tokens', response.data)
        self.assertIn('totp', response.data['methods'])
        return response.data['challenge_token']

    def test_password_then_totp_issues_tokens_with_amr_and_mfa_at(self):
        challenge = self.challenge()
        before = int(time.time())
        response = self.client.post(
            VERIFY, {'challenge_token': challenge, 'method': 'totp', 'code': totp_code(self.secret)}
        )
        self.assertEqual(response.status_code, 200, response.data)
        access = AccessToken(response.data['tokens']['access'])
        self.assertIn('otp', access['amr'])
        self.assertIn('mfa', access['amr'])
        self.assertGreaterEqual(access['mfa_at'], before)
        self.assertEqual(response.data['user']['username'], 'olga')
        self.bearer(response.data['tokens']['access'])
        self.assertEqual(self.client.get(PROFILE).status_code, 200)

    def test_the_challenge_token_is_not_an_access_or_refresh_token(self):
        challenge = self.challenge()
        self.bearer(challenge)
        self.assertEqual(self.client.get(PROFILE).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(REFRESH, {'refresh': challenge}).status_code, 401)

    def test_an_access_token_is_not_a_challenge_token(self):
        access = str(AccessToken.for_user(self.user))
        response = self.client.post(
            VERIFY, {'challenge_token': access, 'method': 'totp', 'code': totp_code(self.secret)}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['code'], 'mfa_token_invalid')

    def test_the_challenge_token_is_single_use(self):
        challenge = self.challenge()
        first = self.client.post(
            VERIFY, {'challenge_token': challenge, 'method': 'totp', 'code': totp_code(self.secret)}
        )
        self.assertEqual(first.status_code, 200)
        again = self.client.post(
            VERIFY, {'challenge_token': challenge, 'method': 'totp', 'code': totp_code(self.secret, step_offset=1)}
        )
        self.assertEqual(again.status_code, 401)

    def test_an_expired_challenge_token_is_refused(self):
        token = MFAChallengeToken.for_user(self.user)
        token.set_exp(lifetime=-timedelta(seconds=1))
        response = self.client.post(
            VERIFY, {'challenge_token': str(token), 'method': 'totp', 'code': totp_code(self.secret)}
        )
        self.assertEqual(response.status_code, 401)

    def test_a_challenge_allows_five_wrong_codes(self):
        challenge = self.challenge()
        wrong = '000000' if totp_code(self.secret) != '000000' else '111111'
        for _ in range(5):
            response = self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'totp', 'code': wrong})
            self.assertIn(response.status_code, (400, 429))
        # Even the right code is refused now: sign in again.
        response = self.client.post(
            VERIFY, {'challenge_token': challenge, 'method': 'totp', 'code': totp_code(self.secret)}
        )
        self.assertIn(response.status_code, (401, 429))

    def test_a_replayed_totp_code_is_refused_at_the_next_login(self):
        code = totp_code(self.secret)
        self.assertEqual(
            self.client.post(VERIFY, {'challenge_token': self.challenge(), 'method': 'totp', 'code': code}).status_code,
            200,
        )
        response = self.client.post(VERIFY, {'challenge_token': self.challenge(), 'method': 'totp', 'code': code})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'mfa_invalid')

    def test_a_recovery_code_logs_in_once_and_the_user_is_told(self):
        codes = recovery.regenerate(self.user)
        response = self.client.post(
            VERIFY, {'challenge_token': self.challenge(), 'method': 'recovery_code', 'code': codes[0]}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('rec', AccessToken(response.data['tokens']['access'])['amr'])
        response = self.client.post(
            VERIFY, {'challenge_token': self.challenge(), 'method': 'recovery_code', 'code': codes[0]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            Notification.objects.filter(user=self.user, type='security_alert', title__icontains='recovery').exists()
        )
        self.assertTrue(Job.objects.filter(kind='send_email', payload__subject__icontains='recovery code').exists())

    def test_methods_list_recovery_codes_and_passkeys(self):
        recovery.regenerate(self.user)
        self.assertEqual(self.login(self.user).data['methods'], ['totp', 'recovery_code'])

    def test_failed_attempts_are_logged_without_the_code(self):
        challenge = self.challenge()
        with self.assertLogs('mfa', level='WARNING') as logs:
            self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'totp', 'code': '123456'})
        joined = '\n'.join(logs.output)
        self.assertIn('mfa.verify_failed', joined)
        self.assertIn(f'user={self.user.pk}', joined)
        self.assertNotIn('123456', joined)


class EnforcementTests(MFABase):
    def test_an_organizer_without_2fa_gets_only_an_enrollment_token(self):
        organizer = self.make_user('org', role='organizer')
        response = self.login(organizer)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['mfa_enrollment_required'])
        self.assertNotIn('tokens', response.data)
        enrollment = response.data['enrollment_token']
        # It is not an access token...
        self.bearer(enrollment)
        self.assertEqual(self.client.get(PROFILE).status_code, 401)
        self.assertEqual(self.client.get('/api/v1/my-events/').status_code, 401)
        # ...nor a refresh token.
        self.client.credentials()
        self.assertEqual(self.client.post(REFRESH, {'refresh': enrollment}).status_code, 401)

    def test_staff_and_superusers_must_enroll_too(self):
        for user in (self.make_user('staff', is_staff=True), self.make_user('root', is_superuser=True)):
            with self.subTest(user=user.username):
                self.assertTrue(self.login(user).data['mfa_enrollment_required'])

    @override_settings(MFA_REQUIRED_ROLES=[])
    def test_with_enforcement_off_an_organizer_signs_in_with_the_password(self):
        response = self.login(self.make_user('org', role='organizer'))
        self.assertIn('tokens', response.data)

    def test_enrollment_with_the_enrollment_token_ends_in_a_full_session(self):
        organizer = self.make_user('org', role='organizer')
        enrollment = self.login(organizer).data['enrollment_token']
        self.bearer(enrollment)
        setup = self.client.post('/api/v1/auth/mfa/totp/setup/')
        self.assertEqual(setup.status_code, 200, setup.data)
        self.assertTrue(setup.data['otpauth_uri'].startswith('otpauth://totp/EventHub:'))
        # Not active until the first code is confirmed.
        self.assertFalse(TOTPDevice.objects.get(user=organizer).confirmed)
        self.client.credentials()
        self.assertTrue(self.login(organizer).data.get('mfa_enrollment_required'))
        self.bearer(enrollment)

        bad = self.client.post('/api/v1/auth/mfa/totp/confirm/', {'code': '000000'})
        self.assertEqual(bad.status_code, 400)
        confirm = self.client.post('/api/v1/auth/mfa/totp/confirm/', {'code': totp_code(setup.data['secret'])})
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.assertEqual(len(confirm.data['recovery_codes']), 10)
        access = AccessToken(confirm.data['tokens']['access'])
        self.assertIn('mfa_at', access.payload)
        # The enrollment token is spent.
        self.assertEqual(self.client.post('/api/v1/auth/mfa/totp/setup/').status_code, 401)
        # The new session works; the next login asks for the factor.
        self.bearer(confirm.data['tokens']['access'])
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        self.client.credentials()
        self.assertTrue(self.login(organizer).data['mfa_required'])

    def test_an_enrollment_token_cannot_add_a_factor_once_one_exists(self):
        organizer = self.make_user('org', role='organizer')
        enrollment = str(MFAEnrollmentToken.for_user(organizer))
        enroll_totp(organizer)
        self.bearer(enrollment)
        self.assertEqual(self.client.post('/api/v1/auth/mfa/webauthn/register/options/').status_code, 401)

    def test_a_password_only_access_token_is_refused_for_an_organizer(self):
        organizer = self.make_user('org', role='organizer')
        self.bearer(str(RefreshToken.for_user(organizer).access_token))
        response = self.client.get(PROFILE)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['code'], 'mfa_required')

    def test_a_password_only_token_stops_working_once_an_attendee_enables_2fa(self):
        attendee = self.make_user('ann')
        access = self.login(attendee).data['tokens']['access']
        self.bearer(access)
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        enroll_totp(attendee)
        self.assertEqual(self.client.get(PROFILE).status_code, 401)


class RefreshTests(MFABase):
    def test_refresh_keeps_the_original_mfa_at(self):
        user = self.make_user('olga', role='organizer')
        refresh = RefreshToken.for_user(user)
        refresh['amr'] = ['pwd', 'otp', 'mfa']
        refresh['mfa_at'] = int(time.time()) - 3600
        response = self.client.post(REFRESH, {'refresh': str(refresh)})
        self.assertEqual(response.status_code, 200)
        access = AccessToken(response.data['access'])
        self.assertEqual(access['mfa_at'], refresh['mfa_at'])
        self.assertEqual(AccessToken(response.data['access'])['amr'], ['pwd', 'otp', 'mfa'])
        new_refresh = RefreshToken(response.data['refresh'])
        self.assertEqual(new_refresh['mfa_at'], refresh['mfa_at'])
        # So the refreshed token is fine for normal calls but not for a
        # sensitive one (the proof is an hour old).
        enroll_totp(user)
        self.bearer(response.data['access'])
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/mfa/recovery-codes/regenerate/').status_code, 403)
