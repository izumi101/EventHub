"""One-click unsubscribe (RFC 8058): signed tokens, the public endpoint and
the headers / footer of optional and mandatory emails."""

from urllib.parse import parse_qs, urlsplit

from django.core import signing
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from . import types, unsubscribe
from .models import NotificationPreference
from .service import notify
from .tests import WorldMixin, email_jobs

URL = '/api/v1/notifications/unsubscribe/'


def token_of(header: str) -> str:
    return parse_qs(urlsplit(header.strip('<>')).query)['token'][0]


@override_settings(FRONTEND_URL='https://tickets.example.com')
class UnsubscribeHeaderTests(WorldMixin, APITestCase):
    def setUp(self):
        self.make_world()

    def test_optional_emails_carry_both_headers_and_a_footer_link(self):
        notify(self.alice, types.SEAT_AVAILABLE, event=self.event, minutes=30)
        payload = email_jobs(self.alice).get().payload
        header = payload['headers']['List-Unsubscribe']
        self.assertTrue(header.startswith('<https://tickets.example.com/api/v1/notifications/unsubscribe/?token='))
        self.assertTrue(header.endswith('>'))
        self.assertEqual(payload['headers']['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')
        token = token_of(header)
        self.assertEqual(unsubscribe.read_token(token), (self.alice, types.SEAT_AVAILABLE))
        self.assertIn(unsubscribe.page_url(token), payload['body'])

    def test_mandatory_emails_have_no_unsubscribe_header_or_link(self):
        for type_key, data in (
            (types.EVENT_CANCELLED, {'refund': 'refunded'}),
            (types.PAYMENT_REFUNDED, {'amount': '10.00', 'currency': 'usd'}),
            (types.SECURITY_ALERT, {'title': 'Two-factor is on', 'body': 'You turned it on.'}),
        ):
            with self.subTest(type_key):
                email_jobs().delete()
                notify(self.alice, type_key, event=self.event, **data)
                payload = email_jobs(self.alice).get().payload
                self.assertFalse(payload.get('headers'))
                self.assertNotIn('unsubscribe', (payload['body'] + payload['html_body']).lower())

    def test_the_worker_sends_the_headers(self):
        from django.core import mail

        from jobs.queue import run_due_jobs

        notify(self.alice, types.SEAT_AVAILABLE, event=self.event, minutes=30)
        run_due_jobs()
        sent = mail.outbox[-1].message()
        self.assertIn('/api/v1/notifications/unsubscribe/?token=', sent['List-Unsubscribe'])
        self.assertEqual(sent['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')


class UnsubscribeEndpointTests(WorldMixin, APITestCase):
    def setUp(self):
        self.make_world()
        # No session, no JWT, CSRF enforced: as a mail provider would call it.
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = unsubscribe.make_token(self.alice, types.EVENT_REMINDER)

    def disabled(self, user=None):
        preference = NotificationPreference.objects.filter(user=user or self.alice).first()
        return preference.email_disabled if preference else []

    def test_get_describes_the_link_and_changes_nothing(self):
        for _ in range(3):
            response = self.client.get(URL, {'token': self.token})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, {'type': types.EVENT_REMINDER, 'label': 'Event reminder'})
        self.assertFalse(NotificationPreference.objects.exists())

    def test_one_click_post_switches_the_email_off_idempotently(self):
        # RFC 8058: the provider POSTs this form body to the List-Unsubscribe URL.
        for _ in range(2):
            response = self.client.post(
                f'{URL}?token={self.token}',
                'List-Unsubscribe=One-Click',
                content_type='application/x-www-form-urlencoded',
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.data['type'], types.EVENT_REMINDER)
        self.assertEqual(self.disabled(), [types.EVENT_REMINDER])
        # Other types and other users are untouched.
        self.assertTrue(NotificationPreference.objects.get(user=self.alice).email_enabled(types.SEAT_AVAILABLE))
        self.assertEqual(self.disabled(self.bob), [])

    def test_post_with_the_token_in_a_json_body(self):
        response = self.client.post(URL, {'token': self.token}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.disabled(), [types.EVENT_REMINDER])

    def test_existing_opt_outs_are_kept(self):
        NotificationPreference.objects.create(user=self.alice, email_disabled=[types.SEAT_AVAILABLE], language='ru')
        self.client.post(f'{URL}?token={self.token}')
        preference = NotificationPreference.objects.get(user=self.alice)
        self.assertEqual(preference.email_disabled, [types.EVENT_REMINDER, types.SEAT_AVAILABLE])
        self.assertEqual(preference.language, 'ru')

    def test_an_unsubscribed_type_is_no_longer_emailed(self):
        self.client.post(f'{URL}?token={self.token}')
        notify(self.alice, types.EVENT_REMINDER, event=self.event)
        self.assertFalse(email_jobs(self.alice).exists())

    def test_bad_tokens_are_refused_alike(self):
        signer = signing.Signer(salt=unsubscribe.SALT)
        deleted = unsubscribe.make_token(self.bob, types.EVENT_REMINDER)
        self.bob.delete()
        bad = {
            'missing': None,
            'empty': '',
            'garbage': 'not-a-token',
            'tampered': self.token[:-2] + ('AA' if not self.token.endswith('AA') else 'BB'),
            'other salt': signing.Signer(salt='something.else').sign_object([self.alice.pk, types.EVENT_REMINDER]),
            'mandatory type': signer.sign_object([self.alice.pk, types.EVENT_CANCELLED]),
            'unknown type': signer.sign_object([self.alice.pk, 'password_reset']),
            'bad shape': signer.sign_object({'u': self.alice.pk}),
            'string id': signer.sign_object([str(self.alice.pk), types.EVENT_REMINDER]),
            'deleted user': deleted,
            'too long': 'x' * 600,
        }
        for name, token in bad.items():
            with self.subTest(name):
                params = {} if token is None else {'token': token}
                for response in (self.client.get(URL, params), self.client.post(URL, params, format='json')):
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.data, {'error': 'This unsubscribe link is invalid.'})
        self.assertFalse(NotificationPreference.objects.exists())

    def test_tokens_do_not_expire_and_are_stable(self):
        self.assertEqual(self.token, unsubscribe.make_token(self.alice, types.EVENT_REMINDER))
        self.assertNotEqual(self.token, unsubscribe.make_token(self.bob, types.EVENT_REMINDER))
        self.assertNotEqual(self.token, unsubscribe.make_token(self.alice, types.SEAT_AVAILABLE))

    def test_the_legacy_alias_serves_it_too(self):
        self.assertEqual(self.client.get('/api/notifications/unsubscribe/', {'token': self.token}).status_code, 200)

    def test_it_is_throttled(self):
        from unittest.mock import patch

        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle

        from .views import UnsubscribeView

        cache.clear()
        with (
            patch.object(UnsubscribeView, 'throttle_classes', [ScopedRateThrottle]),
            patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'unsubscribe': '2/min'}),
        ):
            codes = [self.client.get(URL, {'token': self.token}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
