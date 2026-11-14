"""Email codes as a second factor (ADR 0002, amendment 1): enrollment,
sign-in, step-up, the code's lifetime / attempt budget / single use, the
sending limits, enumeration-safe answers and the policy switch for roles that
must use 2FA."""

import re
from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from jobs.models import Job

from .models import EmailCode, EmailFactor, WebAuthnCredential
from .testing import authenticate_with_recent_mfa, enroll_totp

LOGIN = '/api/v1/auth/login/'
VERIFY = '/api/v1/auth/mfa/login/verify/'
LOGIN_SEND = '/api/v1/auth/mfa/login/email/send/'
SEND = '/api/v1/auth/mfa/email/send/'
ENABLE = '/api/v1/auth/mfa/email/enable/'
DISABLE = '/api/v1/auth/mfa/email/disable/'
STATUS = '/api/v1/auth/mfa/status/'
STEP_UP = '/api/v1/auth/mfa/step-up/'
PROFILE = '/api/v1/auth/profile/'
CODE_RE = re.compile(r'code is: (\d{6})')


class EmailFactorBase(APITestCase):
    password = 'Str0ng-pass!'

    def setUp(self):
        cache.clear()

    def make_user(self, name, role='attendee', **flags):
        from django.contrib.auth.models import User

        user = User.objects.create_user(name, f'{name}@example.com', self.password, **flags)
        user.profile.role = role
        user.profile.save()
        return user

    def login(self, user):
        return self.client.post(LOGIN, {'username': user.username, 'password': self.password})

    def bearer(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def last_code(self, user):
        """The code in the newest email to `user` (the outbox job's body)."""
        job = Job.objects.filter(kind='send_email', payload__to=[user.email]).order_by('-id').first()
        self.assertIsNotNone(job, 'no email was queued')
        match = CODE_RE.search(job.payload['body'])
        self.assertIsNotNone(match, job.payload['body'])
        return match.group(1)

    def code_emails(self, user):
        return Job.objects.filter(kind='send_email', payload__to=[user.email], payload__body__icontains='code is:')

    def allow_next_send(self, user):
        """Move the user's codes back in time past the one-a-minute limit."""
        EmailCode.objects.filter(user=user).update(created_at=timezone.now() - timedelta(minutes=2))

    def enable_email(self, user):
        EmailFactor.objects.create(user=user, confirmed_at=timezone.now())


class EmailEnrollmentTests(EmailFactorBase):
    def test_an_organizer_enrolls_with_an_email_code_and_gets_a_full_session(self):
        organizer = self.make_user('org', role='organizer')
        enrollment = self.login(organizer).data['enrollment_token']
        self.bearer(enrollment)

        sent = self.client.post(SEND, {'purpose': 'enroll'})
        self.assertEqual(sent.status_code, 200, sent.data)
        self.assertEqual(sent.data, {'sent': True, 'expires_in': 600, 'resend_in': 60})
        code = self.last_code(organizer)

        wrong = '000000' if code != '000000' else '111111'
        self.assertEqual(self.client.post(ENABLE, {'code': wrong}).status_code, 400)
        response = self.client.post(ENABLE, {'code': code})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['recovery_codes']), 10)
        access = AccessToken(response.data['tokens']['access'])
        self.assertIn('email', access['amr'])
        self.assertIn('mfa_at', access.payload)
        self.assertTrue(EmailFactor.objects.filter(user=organizer).exists())

        # The enrollment token is spent; the new session works.
        self.assertEqual(self.client.post(SEND, {'purpose': 'enroll'}).status_code, 401)
        self.bearer(response.data['tokens']['access'])
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        status = self.client.get(STATUS).data
        self.assertTrue(status['enabled'])
        self.assertTrue(status['email_enabled'])
        self.assertEqual(status['methods'], ['email', 'recovery_code'])

        # The next sign-in asks for the second factor.
        self.client.credentials()
        login = self.login(organizer).data
        self.assertTrue(login['mfa_required'])
        self.assertEqual(login['methods'], ['email', 'recovery_code'])

    def test_only_a_hash_of_the_code_is_stored(self):
        user = self.make_user('ann')
        authenticate_with_recent_mfa(self.client, user)
        self.client.post(SEND, {'purpose': 'enroll'})
        code = self.last_code(user)
        row = EmailCode.objects.get(user=user)
        self.assertEqual(len(row.code_hash), 64)
        self.assertNotIn(code, row.code_hash)
        self.assertNotIn(code, str(row))

    def test_adding_email_to_an_account_with_a_factor_needs_step_up(self):
        user = self.make_user('ann')
        enroll_totp(user)
        authenticate_with_recent_mfa(self.client, user, age_seconds=11 * 60)
        response = self.client.post(SEND, {'purpose': 'enroll'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'mfa_step_up_required')

        authenticate_with_recent_mfa(self.client, user)
        self.assertEqual(self.client.post(SEND, {'purpose': 'enroll'}).status_code, 200)
        response = self.client.post(ENABLE, {'code': self.last_code(user)})
        self.assertEqual(response.status_code, 200, response.data)
        # Not the first factor: no new recovery codes, no new session.
        self.assertIsNone(response.data['recovery_codes'])
        self.assertIsNone(response.data['tokens'])

    def test_enabling_twice_is_a_conflict(self):
        user = self.make_user('ann')
        self.enable_email(user)
        authenticate_with_recent_mfa(self.client, user)
        response = self.client.post(SEND, {'purpose': 'enroll'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'mfa_email_exists')

    def test_an_account_without_an_email_address_cannot_use_email_codes(self):
        user = self.make_user('ann')
        user.email = ''
        user.save()
        authenticate_with_recent_mfa(self.client, user)
        response = self.client.post(SEND, {'purpose': 'enroll'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'mfa_no_email')

    def test_an_enrollment_token_cannot_ask_for_a_step_up_code(self):
        organizer = self.make_user('org', role='organizer')
        self.bearer(self.login(organizer).data['enrollment_token'])
        response = self.client.post(SEND, {'purpose': 'step_up'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.code_emails(organizer).exists())


class EmailLoginTests(EmailFactorBase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user('olga', role='organizer')
        self.enable_email(self.user)

    def challenge(self):
        response = self.login(self.user)
        self.assertTrue(response.data['mfa_required'])
        self.assertIn('email', response.data['methods'])
        return response.data['challenge_token']

    def test_password_then_email_code_signs_in(self):
        challenge = self.challenge()
        sent = self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        self.assertEqual(sent.status_code, 200, sent.data)
        job = self.code_emails(self.user).get()
        self.assertIn('sign-in', job.payload['subject'])
        response = self.client.post(
            VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': self.last_code(self.user)}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('email', AccessToken(response.data['tokens']['access'])['amr'])
        self.assertIsNotNone(EmailFactor.objects.get(user=self.user).last_used_at)

    def test_a_code_works_once(self):
        challenge = self.challenge()
        self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        code = self.last_code(self.user)
        first = self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': code})
        self.assertEqual(first.status_code, 200)
        again = self.client.post(VERIFY, {'challenge_token': self.challenge(), 'method': 'email', 'code': code})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.data['code'], 'mfa_invalid')

    def test_an_expired_code_is_refused(self):
        challenge = self.challenge()
        self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        code = self.last_code(self.user)
        EmailCode.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': code})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'mfa_invalid')

    def test_five_wrong_guesses_burn_the_code(self):
        self.client.post(LOGIN_SEND, {'challenge_token': self.challenge()})
        code = self.last_code(self.user)
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            # A fresh challenge each time: the challenge's own budget is not what is tested here.
            cache.clear()
            response = self.client.post(VERIFY, {'challenge_token': self.challenge(), 'method': 'email', 'code': wrong})
            self.assertIn(response.status_code, (400, 429))
        self.assertTrue(EmailCode.objects.get(user=self.user).is_used)
        cache.clear()
        from .models import MFAState

        MFAState.objects.filter(user=self.user).update(failed_attempts=0, locked_until=None)
        response = self.client.post(VERIFY, {'challenge_token': self.challenge(), 'method': 'email', 'code': code})
        self.assertEqual(response.status_code, 400)

    def test_a_new_code_replaces_the_previous_one(self):
        challenge = self.challenge()
        self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        old = self.last_code(self.user)
        self.allow_next_send(self.user)
        self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        new = self.last_code(self.user)
        if old != new:
            response = self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': old})
            self.assertEqual(response.status_code, 400)
        response = self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': new})
        self.assertEqual(response.status_code, 200, response.data)

    def test_a_step_up_code_does_not_sign_in(self):
        authenticate_with_recent_mfa(self.client, self.user)
        self.client.post(SEND, {'purpose': 'step_up'})
        code = self.last_code(self.user)
        self.client.force_authenticate(None)
        response = self.client.post(VERIFY, {'challenge_token': self.challenge(), 'method': 'email', 'code': code})
        self.assertEqual(response.status_code, 400)

    def test_sending_is_limited_to_one_a_minute_and_five_an_hour(self):
        challenge = self.challenge()
        self.assertEqual(self.client.post(LOGIN_SEND, {'challenge_token': challenge}).status_code, 200)
        again = self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        self.assertEqual(again.status_code, 429)
        self.assertEqual(again.data['code'], 'mfa_email_throttled')
        self.assertTrue(1 <= again.data['retry_after'] <= 60)
        for _ in range(4):
            self.allow_next_send(self.user)
            self.assertEqual(self.client.post(LOGIN_SEND, {'challenge_token': challenge}).status_code, 200)
        self.allow_next_send(self.user)
        sixth = self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        self.assertEqual(sixth.status_code, 429)
        self.assertGreater(sixth.data['retry_after'], 60)
        self.assertEqual(self.code_emails(self.user).count(), 5)

    def test_the_limits_are_per_purpose(self):
        # Turning email codes on and signing in right after must not be blocked.
        authenticate_with_recent_mfa(self.client, self.user)
        self.assertEqual(self.client.post(SEND, {'purpose': 'step_up'}).status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(LOGIN_SEND, {'challenge_token': self.challenge()}).status_code, 200)

    def test_a_bad_challenge_token_sends_nothing(self):
        response = self.client.post(LOGIN_SEND, {'challenge_token': 'nope'})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.code_emails(self.user).exists())


class EnumerationTests(EmailFactorBase):
    def test_the_send_answer_is_the_same_with_or_without_email_codes(self):
        with_email = self.make_user('with', role='organizer')
        self.enable_email(with_email)
        without = self.make_user('without', role='organizer')
        enroll_totp(without)

        a = self.client.post(LOGIN_SEND, {'challenge_token': self.login(with_email).data['challenge_token']})
        b = self.client.post(LOGIN_SEND, {'challenge_token': self.login(without).data['challenge_token']})
        self.assertEqual((a.status_code, a.data), (b.status_code, b.data))
        # ...but only the user with email codes gets an email.
        self.assertEqual(self.code_emails(with_email).count(), 1)
        self.assertFalse(self.code_emails(without).exists())
        # And the user without email codes can't sign in with one.
        challenge = self.login(without).data['challenge_token']
        for code in ('123456', '000000'):
            response = self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': code})
            self.assertEqual(response.status_code, 400)

    def test_wrong_expired_and_used_codes_get_the_same_answer(self):
        user = self.make_user('olga', role='organizer')
        self.enable_email(user)
        challenge = self.login(user).data['challenge_token']
        self.client.post(LOGIN_SEND, {'challenge_token': challenge})
        code = self.last_code(user)
        wrong = '000000' if code != '000000' else '111111'
        answers = [self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': wrong}).data]
        EmailCode.objects.filter(user=user).update(expires_at=timezone.now() - timedelta(seconds=1))
        answers.append(self.client.post(VERIFY, {'challenge_token': challenge, 'method': 'email', 'code': code}).data)
        self.assertEqual(answers[0], answers[1])
        self.assertEqual(answers[0]['code'], 'mfa_invalid')


class EmailStepUpAndRemovalTests(EmailFactorBase):
    def test_step_up_with_an_email_code(self):
        user = self.make_user('olga', role='organizer')
        self.enable_email(user)
        authenticate_with_recent_mfa(self.client, user, age_seconds=11 * 60)
        self.assertEqual(self.client.post(SEND, {'purpose': 'step_up'}).status_code, 200)
        job = self.code_emails(user).get()
        self.assertIn('confirm', job.payload['subject'])
        response = self.client.post(STEP_UP, {'method': 'email', 'code': self.last_code(user)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('email', AccessToken(response.data['access'])['amr'])

    def test_a_step_up_code_needs_email_codes_turned_on(self):
        user = self.make_user('ann')
        enroll_totp(user)
        authenticate_with_recent_mfa(self.client, user)
        response = self.client.post(SEND, {'purpose': 'step_up'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'mfa_email_not_enabled')

    def test_turning_email_codes_off_needs_step_up_and_keeps_the_last_required_factor(self):
        organizer = self.make_user('org', role='organizer')
        self.enable_email(organizer)
        authenticate_with_recent_mfa(self.client, organizer, age_seconds=11 * 60)
        self.assertEqual(self.client.post(DISABLE).status_code, 403)
        authenticate_with_recent_mfa(self.client, organizer)
        response = self.client.post(DISABLE)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'mfa_required_by_policy')

        enroll_totp(organizer)
        response = self.client.post(DISABLE)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['email_enabled'])
        self.assertTrue(response.data['enabled'])

    def test_an_attendee_turning_off_the_only_factor_turns_2fa_off(self):
        user = self.make_user('ann')
        self.enable_email(user)
        authenticate_with_recent_mfa(self.client, user)
        response = self.client.post(DISABLE)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['enabled'])
        self.client.force_authenticate(None)
        self.assertIn('tokens', self.login(user).data)

    def test_the_last_totp_can_go_when_email_codes_remain(self):
        organizer = self.make_user('org', role='organizer')
        self.enable_email(organizer)
        enroll_totp(organizer)
        authenticate_with_recent_mfa(self.client, organizer)
        response = self.client.delete('/api/v1/auth/mfa/totp/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['methods'], ['email'])

    def test_disable_all_removes_email_codes(self):
        user = self.make_user('ann')
        self.enable_email(user)
        authenticate_with_recent_mfa(self.client, user)
        self.assertEqual(self.client.post('/api/v1/auth/mfa/disable/').status_code, 200)
        self.assertFalse(EmailFactor.objects.filter(user=user).exists())


@override_settings(MFA_EMAIL_ALLOWED_FOR_REQUIRED_ROLES=False)
class EmailNotAllowedForRequiredRolesTests(EmailFactorBase):
    def test_an_organizer_cannot_enroll_with_email(self):
        organizer = self.make_user('org', role='organizer')
        self.bearer(self.login(organizer).data['enrollment_token'])
        response = self.client.post(SEND, {'purpose': 'enroll'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'mfa_email_not_allowed')

    def test_email_codes_alone_do_not_satisfy_the_role_rule(self):
        organizer = self.make_user('org', role='organizer')
        self.enable_email(organizer)
        response = self.login(organizer)
        self.assertTrue(response.data['mfa_enrollment_required'])

    def test_attendees_may_still_use_email_codes(self):
        user = self.make_user('ann')
        self.enable_email(user)
        self.assertEqual(self.login(user).data['methods'], ['email'])


class PasskeyRenameTests(EmailFactorBase):
    def test_a_passkey_can_be_renamed_without_step_up(self):
        user = self.make_user('ann')
        key = WebAuthnCredential.objects.create(user=user, name='Old', credential_id='abc', public_key=b'x')
        authenticate_with_recent_mfa(self.client, user, age_seconds=11 * 60)
        url = f'/api/v1/auth/mfa/webauthn/credentials/{key.pk}/'
        response = self.client.patch(url, {'name': '  Laptop  '})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['passkeys'][0]['name'], 'Laptop')
        self.assertEqual(self.client.patch(url, {'name': '  '}).status_code, 400)
        other = self.make_user('bob')
        authenticate_with_recent_mfa(self.client, other)
        self.assertEqual(self.client.patch(url, {'name': 'Mine'}).status_code, 404)


class AdminEmailVerifyTests(EmailFactorBase):
    def test_staff_with_email_codes_pass_the_admin_second_step(self):
        staff = self.make_user('root', is_staff=True, is_superuser=True)
        self.enable_email(staff)
        self.client.force_login(staff)
        page = self.client.get('/admin/mfa/verify/')
        self.assertContains(page, 'Email me a code')
        self.client.post('/admin/mfa/verify/', {'send_email_code': '1', 'method': 'email', 'code': ''})
        response = self.client.post('/admin/mfa/verify/', {'method': 'email', 'code': self.last_code(staff)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
