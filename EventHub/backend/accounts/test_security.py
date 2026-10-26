"""Regression tests for the auth issues listed in REVIEW.md."""
from django.contrib.auth.models import User
from django.test import RequestFactory, override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import BaseThrottle
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from accounts.models import EmailVerificationCode, PasswordResetCode


class CodeBruteForceTests(APITestCase):
    def test_code_is_burned_after_five_wrong_guesses(self):
        # K7: unlimited guesses at a 6-digit code (throttle was bypassable).
        verification = EmailVerificationCode.create_for_email('new@example.com')
        wrong = '000000' if verification.code != '000000' else '111111'
        for _ in range(5):
            response = self.client.post('/api/auth/register/verify-code/',
                                        {'email': 'new@example.com', 'code': wrong})
            self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/auth/register/verify-code/',
                                    {'email': 'new@example.com', 'code': verification.code})
        self.assertEqual(response.status_code, 400)

    def test_reset_code_has_the_same_budget(self):
        user = User.objects.create_user('victim', 'victim@example.com', 'Str0ng-pass!')
        entry = PasswordResetCode.create_for_user(user)
        wrong = '000000' if entry.code != '000000' else '111111'
        for _ in range(5):
            self.client.post('/api/auth/password-reset/verify/', {'identifier': 'victim', 'code': wrong})
        response = self.client.post('/api/auth/password-reset/verify/',
                                    {'identifier': 'victim', 'code': entry.code})
        self.assertEqual(response.status_code, 400)

    def test_unknown_account_and_wrong_code_look_the_same(self):
        # Important #6: different messages revealed which accounts exist.
        User.objects.create_user('known', 'known@example.com', 'Str0ng-pass!')
        a = self.client.post('/api/auth/password-reset/verify/', {'identifier': 'known', 'code': '123456'})
        b = self.client.post('/api/auth/password-reset/verify/', {'identifier': 'nobody', 'code': '123456'})
        self.assertEqual(a.data, b.data)

    def test_throttle_identity_ignores_spoofed_forwarded_for(self):
        # K7: DRF used the whole client-supplied X-Forwarded-For as identity.
        request = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='6.6.6.6, 203.0.113.7',
                                       REMOTE_ADDR='172.18.0.5')
        self.assertEqual(BaseThrottle().get_ident(request), '203.0.113.7')


class DevCodeTests(APITestCase):
    @override_settings(DEBUG=False, EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_code_is_never_returned_outside_debug(self):
        # K4: without SMTP the code was returned to anyone, bypassing email proof.
        response = self.client.post('/api/auth/register/send-code/', {'email': 'x@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('dev_code', response.data)


class LoginIdentifierTests(APITestCase):
    def test_username_cannot_look_like_an_email(self):
        # Important #4.
        EmailVerificationCode.create_for_email('real@example.com')
        code = EmailVerificationCode.objects.get().code
        response = self.client.post('/api/auth/register/', {
            'username': 'victim@example.com', 'email': 'real@example.com',
            'password': 'Str0ng-pass!', 'password2': 'Str0ng-pass!', 'verification_code': code,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)

    def test_email_login_reaches_the_email_owner(self):
        # A legacy account whose *username* is someone else's email address.
        User.objects.create_user('victim@example.com', 'attacker@example.com', 'Attacker-pass1')
        User.objects.create_user('victim', 'victim@example.com', 'Victim-pass1')
        response = self.client.post('/api/auth/login/', {'username': 'victim@example.com',
                                                         'password': 'Victim-pass1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['username'], 'victim')


class PasswordChangeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', 'Old-pass-123')

    def login(self):
        return self.client.post('/api/auth/login/', {'username': 'alice', 'password': 'Old-pass-123'}).data

    def test_change_revokes_other_sessions(self):
        # Important #5: a stolen refresh token kept working for 7 days.
        stolen = self.login()['tokens']['refresh']
        self.client.force_authenticate(self.user)
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'Old-pass-123', 'new_password': 'Brand-new-pass-9', 'new_password2': 'Brand-new-pass-9',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('refresh', response.data['tokens'])
        self.client.force_authenticate(None)
        refreshed = self.client.post('/api/auth/token/refresh/', {'refresh': stolen})
        self.assertEqual(refreshed.status_code, 401)
        self.assertTrue(OutstandingToken.objects.filter(user=self.user).exists())

    def test_change_applies_password_validators(self):
        self.client.force_authenticate(self.user)
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'Old-pass-123', 'new_password': 'password123', 'new_password2': 'password123',
        })
        self.assertEqual(response.status_code, 400)  # too common
