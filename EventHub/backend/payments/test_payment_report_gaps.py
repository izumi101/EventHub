"""Gap-filling payment tests added for the backend payment QA report.

Each case here had no automated coverage elsewhere:

- the legacy Stripe webhook *view* verifying a real HMAC signature (the other
  tests patch ``stripe.Webhook.construct_event`` away);
- a signed delivery replayed twice changing the books only once;
- a refund larger than the remaining balance;
- a partial refund followed by the remaining balance;
- invoice access control (owner / event team only).
"""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from events.models import Event, Registration
from payments.models import Payment

WEBHOOK_SECRET = 'whsec_report_gap_test'


def _signed(payload: str, secret: str = WEBHOOK_SECRET) -> str:
    """A Stripe-Signature header computed the way Stripe computes it."""
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f'{timestamp}.{payload}'.encode(), hashlib.sha256).hexdigest()
    return f't={timestamp},v1={digest}'


class GapBase(APITestCase):
    def setUp(self):
        self.organizer = User.objects.create_user('gap_org', 'gap_org@example.com', 'Str0ng-pass!')
        self.organizer.profile.role = 'organizer'
        self.organizer.profile.save()
        self.buyer = User.objects.create_user('gap_buyer', 'gap_buyer@example.com', 'Str0ng-pass!')
        self.event = Event.objects.create(
            title='Gap gig',
            description='d',
            organizer=self.organizer,
            date=timezone.now() + timedelta(days=5),
            location='Club',
            price=Decimal('100.00'),
            currency='USD',
            max_participants=50,
            status='published',
        )

    def pending_registration(self):
        return Registration.objects.create(
            user=self.buyer,
            event=self.event,
            status='pending',
            seat_held_until=timezone.now() + timedelta(minutes=10),
        )


@override_settings(STRIPE_MOCK_MODE=False, STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class StripeWebhookRealSignatureTests(GapBase):
    """No patching of ``stripe.Webhook.construct_event``: the SDK verifies."""

    def setUp(self):
        super().setUp()
        self.reg = self.pending_registration()
        Payment.objects.create(registration=self.reg, amount=Decimal('100.00'), stripe_checkout_session_id='cs_gap')
        self.payload = json.dumps(
            {
                'id': 'evt_gap',
                'object': 'event',
                'type': 'checkout.session.completed',
                'created': int(time.time()),
                'data': {
                    'object': {
                        'id': 'cs_gap',
                        'object': 'checkout.session',
                        'payment_intent': 'pi_gap',
                        'payment_status': 'paid',
                        'metadata': {'registration_id': str(self.reg.id)},
                    }
                },
            }
        )

    def post(self, signature):
        headers = {} if signature is None else {'HTTP_STRIPE_SIGNATURE': signature}
        return self.client.post('/api/payments/webhook/', data=self.payload, content_type='application/json', **headers)

    def test_a_forged_signature_is_rejected_and_changes_nothing(self):
        for signature in (_signed(self.payload, secret='whsec_attacker'), 't=1,v1=deadbeef', 'garbage', None):
            with self.subTest(signature=str(signature)[:20]):
                self.assertEqual(self.post(signature).status_code, 400)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.status, 'pending')
        self.assertEqual(Payment.objects.get(registration=self.reg).status, 'pending')

    def test_a_tampered_body_with_a_valid_signature_of_another_body_is_rejected(self):
        signature = _signed(self.payload)
        self.payload = self.payload.replace('pi_gap', 'pi_evil')
        self.assertEqual(self.post(signature).status_code, 400)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.status, 'pending')

    def test_a_validly_signed_delivery_confirms_once_even_when_replayed(self):
        signature = _signed(self.payload)
        with patch('stripe.Refund.create') as refund:
            first = self.post(signature)
            second = self.post(signature)
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        refund.assert_not_called()  # a replay of the same session is not a duplicate payment
        self.reg.refresh_from_db()
        payment = Payment.objects.get(registration=self.reg)
        self.assertEqual(self.reg.status, 'confirmed')
        self.assertEqual((payment.status, payment.stripe_payment_intent_id), ('completed', 'pi_gap'))
        self.assertEqual(Payment.objects.filter(registration=self.reg).count(), 1)


@override_settings(STRIPE_MOCK_MODE=False)
class RefundBalanceTests(GapBase):
    def setUp(self):
        super().setUp()
        self.reg = self.pending_registration()
        self.reg.status = 'confirmed'
        self.reg.seat_held_until = None
        self.reg.save()
        self.payment = Payment.objects.create(registration=self.reg, amount=Decimal('100.00'), status='completed')
        self.client.force_authenticate(self.organizer)
        self.url = f'/api/v1/payments/refund/{self.reg.id}/'

    def test_a_refund_above_the_paid_amount_is_refused_and_the_books_are_untouched(self):
        response = self.client.post(self.url, {'amount': '100.01'})
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.reg.refresh_from_db()
        self.assertEqual((self.payment.status, self.payment.refunded_amount), ('completed', Decimal('0')))
        self.assertEqual(self.reg.status, 'confirmed')

    def test_partial_then_remaining_refund_keeps_the_ledger_consistent(self):
        first = self.client.post(self.url, {'amount': '30.00'})
        self.assertEqual(first.status_code, 200)
        self.payment.refresh_from_db()
        self.reg.refresh_from_db()
        self.assertEqual((self.payment.status, self.payment.refunded_amount), ('completed', Decimal('30.00')))
        self.assertEqual(self.reg.status, 'confirmed')  # a partial refund keeps the ticket

        # More than what is left is refused even though it is below the full price.
        self.assertEqual(self.client.post(self.url, {'amount': '70.01'}).status_code, 400)

        last = self.client.post(self.url)  # no amount = the remaining balance
        self.assertEqual(last.status_code, 200)
        self.assertEqual(last.data['refunded_amount'], '100.00')
        self.assertEqual(last.data['net_amount'], '0.00')
        self.payment.refresh_from_db()
        self.reg.refresh_from_db()
        self.assertEqual((self.payment.status, self.payment.refunded_amount), ('refunded', Decimal('100.00')))
        self.assertEqual(self.reg.status, 'cancelled')  # a full refund releases the seat
        self.assertEqual(self.client.post(self.url).status_code, 400)


class InvoiceAccessTests(GapBase):
    def test_only_the_owner_and_the_event_team_can_open_an_invoice(self):
        reg = self.pending_registration()
        reg.status = 'confirmed'
        reg.seat_held_until = None
        reg.save()
        Payment.objects.create(registration=reg, amount=Decimal('100.00'), status='completed')
        stranger = User.objects.create_user('gap_stranger', 'gap_stranger@example.com', 'Str0ng-pass!')
        url = f'/api/v1/payments/invoice/{reg.id}/'

        self.assertEqual(self.client.get(url).status_code, 401)  # anonymous
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.get(url).status_code, 403)  # another attendee: no IDOR
        for allowed in (self.buyer, self.organizer):
            self.client.force_authenticate(allowed)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('text/html', response['Content-Type'])
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get('/api/v1/payments/invoice/999999/').status_code, 404)
