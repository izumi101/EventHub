"""Step-up: every sensitive endpoint wants a second factor from the last
MFA_STEP_UP_MAX_AGE_SECONDS; the step-up endpoint provides it."""

import time
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from bookings.models import Booking
from events.models import Event, EventStaff, RefundRequest, Registration
from payments.models import Payment

from . import recovery
from .test_login import MFABase
from .testing import authenticate_with_recent_mfa, enroll_totp, totp_code

STALE = 11 * 60  # older than the default 10-minute window


class StepUpEndpointTests(MFABase):
    def setUp(self):
        super().setUp()
        self.organizer = self.make_user('org', role='organizer')
        self.secret = enroll_totp(self.organizer)
        self.buyer = self.make_user('buyer')
        self.event = Event.objects.create(
            title='Gig',
            description='d',
            organizer=self.organizer,
            date=timezone.now() + timedelta(days=5),
            location='Club',
            price=Decimal('100.00'),
            status='published',
        )
        self.registration = Registration.objects.create(user=self.buyer, event=self.event, status='confirmed')
        Payment.objects.create(registration=self.registration, amount=Decimal('100'), status='completed')
        self.refund_request = RefundRequest.objects.create(registration=self.registration, reason='ill')
        self.booking = Booking.objects.create(owner=self.buyer, event=self.event, status=Booking.Status.HOLDING)

    def calls(self):
        """(name, method, url, data) of every sensitive organizer/account call."""
        return [
            ('payment refund', 'post', f'/api/v1/payments/refund/{self.registration.pk}/', {}),
            (
                'approve refund request',
                'post',
                f'/api/v1/refund-requests/{self.refund_request.pk}/resolve/',
                {'approve': True},
            ),
            ('booking refund', 'post', f'/api/v1/bookings/{self.booking.pk}/refund/', {}),
            ('event cancellation', 'post', f'/api/v1/events/{self.event.pk}/cancel-event/', {}),
            ('attendee export', 'get', f'/api/v1/events/{self.event.pk}/export-attendees/', None),
            (
                'password change',
                'post',
                '/api/v1/auth/change-password/',
                {'old_password': self.password, 'new_password': 'N3w-pass-word!', 'new_password2': 'N3w-pass-word!'},
            ),
            ('recovery codes', 'post', '/api/v1/auth/mfa/recovery-codes/regenerate/', {}),
            ('remove authenticator', 'delete', '/api/v1/auth/mfa/totp/', None),
            ('disable 2FA', 'post', '/api/v1/auth/mfa/disable/', {}),
        ]

    def call(self, method, url, data):
        with patch('stripe.Refund.create'):
            return (
                getattr(self.client, method)(url, data, format='json')
                if data is not None
                else getattr(self.client, method)(url)
            )

    def test_every_sensitive_call_needs_a_recent_second_factor(self):
        for name, method, url, data in self.calls():
            with self.subTest(name):
                authenticate_with_recent_mfa(self.client, self.organizer, age_seconds=STALE)
                response = self.call(method, url, data)
                self.assertEqual(response.status_code, 403, (name, getattr(response, 'data', None)))
                self.assertEqual(response.data['code'], 'mfa_step_up_required')
                self.assertIn('totp', response.data['methods'])
                self.assertEqual(response.data['max_age'], 600)

    def test_with_a_fresh_proof_the_calls_go_through(self):
        for name, method, url, data in self.calls():
            with self.subTest(name):
                authenticate_with_recent_mfa(self.client, self.organizer)
                response = self.call(method, url, data)
                code = getattr(response, 'data', {}) or {}
                self.assertNotEqual(code.get('code') if isinstance(code, dict) else None, 'mfa_step_up_required')
                self.assertNotEqual(response.status_code, 401, name)

    def test_specific_outcomes_with_a_fresh_proof(self):
        authenticate_with_recent_mfa(self.client, self.organizer)
        with patch('stripe.Refund.create'):
            self.assertEqual(self.client.get(f'/api/v1/events/{self.event.pk}/export-attendees/').status_code, 200)
            response = self.client.post(f'/api/v1/events/{self.event.pk}/cancel-event/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_rejecting_a_refund_request_needs_no_step_up(self):
        authenticate_with_recent_mfa(self.client, self.organizer, age_seconds=STALE)
        response = self.client.post(f'/api/v1/refund-requests/{self.refund_request.pk}/resolve/', {'approve': False})
        self.assertEqual(response.status_code, 200, response.data)

    def test_a_token_without_any_proof_is_refused(self):
        self.client.force_authenticate(self.organizer, token=AccessToken.for_user(self.organizer))
        response = self.client.get(f'/api/v1/events/{self.event.pk}/export-attendees/')
        self.assertEqual(response.data['code'], 'mfa_step_up_required')

    def test_non_managers_get_the_usual_refusal_not_a_prompt(self):
        authenticate_with_recent_mfa(self.client, self.buyer, age_seconds=STALE)
        response = self.client.get(f'/api/v1/events/{self.event.pk}/export-attendees/')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('code', response.data)

    def test_a_team_member_without_2fa_must_set_it_up_first(self):
        helper = self.make_user('helper')
        EventStaff.objects.create(event=self.event, user=helper, role=EventStaff.ROLE_CO_ORGANIZER)
        self.client.force_authenticate(helper, token=AccessToken.for_user(helper))
        response = self.client.get(f'/api/v1/events/{self.event.pk}/export-attendees/')
        self.assertEqual((response.status_code, response.data['code']), (403, 'mfa_enrollment_required'))

    def test_an_attendee_without_2fa_changes_the_password_as_before(self):
        self.client.force_authenticate(self.buyer, token=AccessToken.for_user(self.buyer))
        response = self.client.post(
            '/api/v1/auth/change-password/',
            {'old_password': self.password, 'new_password': 'N3w-pass-word!', 'new_password2': 'N3w-pass-word!'},
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_a_password_change_keeps_the_second_factor_claims(self):
        token = authenticate_with_recent_mfa(self.client, self.organizer)
        response = self.client.post(
            '/api/v1/auth/change-password/',
            {'old_password': self.password, 'new_password': 'N3w-pass-word!', 'new_password2': 'N3w-pass-word!'},
        )
        self.assertEqual(response.status_code, 200, response.data)
        access = AccessToken(response.data['tokens']['access'])
        self.assertEqual(access['mfa_at'], token['mfa_at'])


class StepUpFlowTests(MFABase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user('olga', role='organizer')
        self.secret = enroll_totp(self.user)
        self.stale = authenticate_with_recent_mfa(self.client, self.user, age_seconds=STALE)

    def test_step_up_with_totp_returns_a_fresh_access_token(self):
        before = int(time.time())
        response = self.client.post('/api/v1/auth/mfa/step-up/', {'method': 'totp', 'code': totp_code(self.secret)})
        self.assertEqual(response.status_code, 200, response.data)
        access = AccessToken(response.data['access'])
        self.assertGreaterEqual(access['mfa_at'], before)
        self.assertEqual(response.data['valid_until'], access['mfa_at'] + 600)
        self.assertEqual(access['user_id'], str(self.user.pk))
        self.client.force_authenticate(None)
        self.bearer(response.data['access'])
        self.assertEqual(self.client.post('/api/v1/auth/mfa/recovery-codes/regenerate/').status_code, 200)

    def test_step_up_with_a_recovery_code(self):
        code = recovery.regenerate(self.user)[0]
        response = self.client.post('/api/v1/auth/mfa/step-up/', {'method': 'recovery_code', 'code': code})
        self.assertEqual(response.status_code, 200)
        self.assertIn('rec', AccessToken(response.data['access'])['amr'])

    def test_a_wrong_code_gets_no_token(self):
        response = self.client.post('/api/v1/auth/mfa/step-up/', {'method': 'totp', 'code': '000001'})
        self.assertEqual((response.status_code, response.data['code']), (400, 'mfa_invalid'))
        self.assertNotIn('access', response.data)

    def test_status_reports_the_window(self):
        data = self.client.get('/api/v1/auth/mfa/status/').data
        self.assertTrue(data['enabled'])
        self.assertTrue(data['required'])
        self.assertEqual(data['step_up_valid_until'], self.stale['mfa_at'] + 600)
        self.assertEqual(data['step_up_max_age'], 600)
