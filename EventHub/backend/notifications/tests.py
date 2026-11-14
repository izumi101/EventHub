"""Notifications: the service, the email job, the templates, every trigger,
the 24-hour reminder and the preferences API."""

import base64
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import Booking, BookingSeat
from bookings.services import claim_seat, confirm_booking
from events.models import Category, Event, EventSeat, Notification, Registration, SeatMap, WaitlistEntry
from jobs.handlers import build_email_message, enqueue_email
from jobs.models import Job
from jobs.queue import PermanentJobError, run_due_jobs
from payments.models import Payment
from payments.test_freedompay import CALLBACK_PATH, FP_SETTINGS, FakeGateway, FixturesMixin, callback_form

from . import types
from .emails import render_email, ticket_qr_png
from .messages import build_message, ticket_validation_url
from .models import NotificationPreference, SentReminder
from .reminders import send_due_reminders
from .service import notify

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def email_jobs(user=None):
    jobs = Job.objects.filter(kind='send_email')
    if user is not None:
        jobs = jobs.filter(payload__to=[user.email])
    return jobs


class WorldMixin:
    """An organizer, two attendees and a published event in two weeks."""

    def make_world(self):
        cache.clear()
        self.organizer = User.objects.create_user('org', 'org@example.com', 'password123')
        self.alice = User.objects.create_user('alice', 'alice@example.com', 'password123')
        self.bob = User.objects.create_user('bob', 'bob@example.com', 'password123')
        self.category = Category.objects.create(name='Tech', icon='cpu')
        self.event = self.make_event()

    def make_event(self, *, days=14, price=Decimal('0'), currency='USD', **extra):
        return Event.objects.create(
            title=extra.pop('title', 'Almaty Product Conference'),
            description='Talks',
            organizer=self.organizer,
            category=self.category,
            date=timezone.now() + timedelta(days=days),
            location='Palace of Schoolchildren',
            address='Dostyk Ave 1, Almaty',
            price=price,
            currency=currency,
            max_participants=100,
            status='published',
            **extra,
        )

    def confirmed(self, user, event=None, seat=None):
        return Registration.objects.create(user=user, event=event or self.event, status='confirmed', seat=seat)

    def seat(self, event=None, row=1, col=1):
        seat_map, _ = SeatMap.objects.get_or_create(event=event or self.event, defaults={'rows': 5, 'cols': 5})
        return EventSeat.objects.create(seat_map=seat_map, row=row, col=col, price_zone='vip', is_available=False)

    def assertNotified(self, user, type_key, *, emails=1):
        """Exactly one in-app row of this type, and `emails` email jobs."""
        self.assertEqual(Notification.objects.filter(user=user, type=type_key).count(), 1, type_key)
        self.assertEqual(email_jobs(user).count(), emails, f'{type_key} emails to {user.username}')


# ───────────────────────── service ─────────────────────────


class NotifyServiceTests(WorldMixin, TestCase):
    def setUp(self):
        self.make_world()
        self.registration = self.confirmed(self.alice, seat=self.seat())

    def notify_ticket(self, user=None):
        return notify(
            user or self.alice,
            types.TICKET_PURCHASED,
            event=self.event,
            registration=self.registration,
            amount=Decimal('5000.00'),
            currency='kzt',
        )

    def test_writes_the_in_app_row_and_one_email_job(self):
        notification = self.notify_ticket()
        self.assertTrue(notification.email_queued)
        self.assertNotified(self.alice, types.TICKET_PURCHASED)
        payload = email_jobs(self.alice).get().payload
        self.assertEqual(payload['to'], ['alice@example.com'])
        self.assertEqual(payload['subject'], 'Your ticket for Almaty Product Conference')
        self.assertIn('Almaty Product Conference', payload['body'])
        self.assertIn('cid:ticket-qr-0', payload['html_body'])
        self.assertEqual(payload['headers'], {'List-Unsubscribe': '<http://localhost:4200/profile/notifications>'})
        attachment = payload['attachments'][0]
        self.assertEqual((attachment['mimetype'], attachment['cid']), ('image/png', 'ticket-qr-0'))
        self.assertTrue(base64.b64decode(attachment['content_b64']).startswith(PNG_MAGIC))

    def test_an_opted_out_type_gets_the_in_app_row_but_no_email(self):
        NotificationPreference.objects.create(user=self.alice, email_disabled=[types.TICKET_PURCHASED])
        notification = self.notify_ticket()
        self.assertFalse(notification.email_queued)
        self.assertNotified(self.alice, types.TICKET_PURCHASED, emails=0)

    def test_a_mandatory_type_is_emailed_despite_a_stale_opt_out(self):
        NotificationPreference.objects.create(user=self.alice, email_disabled=[types.EVENT_CANCELLED])
        notify(self.alice, types.EVENT_CANCELLED, event=self.event, refund='refunded')
        self.assertNotified(self.alice, types.EVENT_CANCELLED)

    def test_a_user_without_an_email_address_gets_only_the_in_app_row(self):
        User.objects.filter(pk=self.alice.pk).update(email='')
        self.alice.refresh_from_db()
        self.notify_ticket()
        self.assertEqual(Notification.objects.filter(user=self.alice).count(), 1)
        self.assertFalse(email_jobs().exists())

    def test_in_app_only_types_send_no_email(self):
        notify(self.alice, types.REVIEW_REMINDER, event=self.event)
        self.assertNotified(self.alice, types.REVIEW_REMINDER, emails=0)

    def test_a_rolled_back_transaction_leaves_neither_row_nor_email(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.notify_ticket()
            raise RuntimeError('the business change failed')
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(email_jobs().exists())

    def test_a_failing_notification_does_not_break_the_callers_transaction(self):
        with transaction.atomic():
            with self.assertLogs('notifications.service', 'ERROR'):
                # Missing `registration`: the builder raises.
                self.assertIsNone(notify(self.alice, types.TICKET_PURCHASED, event=self.event))
            Category.objects.create(name='Still writable', icon='x')
        self.assertTrue(Category.objects.filter(name='Still writable').exists())
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(email_jobs().exists())

    def test_unknown_types_are_rejected(self):
        with self.assertLogs('notifications.service', 'ERROR'):
            self.assertIsNone(notify(self.alice, 'no_such_type', event=self.event))


# ───────────────────────── rendering ─────────────────────────


@override_settings(NOTIFICATION_TIME_ZONE='Asia/Almaty', FRONTEND_URL='https://tickets.example.com')
class RenderingTests(WorldMixin, TestCase):
    def setUp(self):
        self.make_world()
        self.event.date = datetime(2026, 12, 5, 13, 0, tzinfo=UTC)
        self.event.save(update_fields=['date'])
        self.registration = self.confirmed(self.alice, seat=self.seat(row=3, col=7))

    def render(self, type_key=types.TICKET_PURCHASED, **data):
        data.setdefault('registration', self.registration)
        message = build_message(type_key, self.alice, self.event, data)
        return render_email(type_key, message)

    def test_the_e_ticket_has_event_date_venue_seat_and_qr(self):
        email = self.render(amount=Decimal('5000.00'), currency='kzt')
        for part in (email['html_body'], email['body']):
            self.assertIn('Almaty Product Conference', part)
            self.assertIn('Sat, 5 Dec 2026, 18:00 (Asia/Almaty)', part)
            self.assertIn('Palace of Schoolchildren, Dostyk Ave 1, Almaty', part)
            self.assertIn('Row 3 · Seat 7 (VIP)', part)
            self.assertIn('5000.00 KZT', part)
            self.assertIn(f'#{str(self.registration.ticket_uuid)[:8].upper()}', part)
            self.assertIn('https://tickets.example.com/profile/notifications', part)
        self.assertIn('<img src="cid:ticket-qr-0"', email['html_body'])
        self.assertNotIn('<', email['body'])

    def test_the_qr_code_encodes_the_frontend_validation_url(self):
        import segno

        url = ticket_validation_url(self.registration.ticket_uuid)
        self.assertEqual(url, f'https://tickets.example.com/validate/{self.registration.ticket_uuid}')
        png = ticket_qr_png(self.registration.ticket_uuid)
        self.assertTrue(png.startswith(PNG_MAGIC))
        reference = io.BytesIO()
        segno.make(url, error='m').save(reference, kind='png', scale=6, border=2)
        self.assertEqual(png, reference.getvalue())
        attachment = self.render(amount=None)['attachments'][0]
        self.assertEqual(base64.b64decode(attachment['content_b64']), png)

    def test_user_content_is_escaped_in_html_and_kept_in_text(self):
        self.event.title = 'Rock <script>alert(1)</script> & Roll'
        self.event.save(update_fields=['title'])
        self.registration.event = self.event
        email = self.render(amount=None)
        self.assertNotIn('<script>', email['html_body'])
        self.assertIn('Rock &lt;script&gt;alert(1)&lt;/script&gt; &amp; Roll', email['html_body'])
        self.assertIn('Rock <script>alert(1)</script> & Roll', email['body'])

    def test_optional_and_mandatory_emails_have_different_footers(self):
        optional = self.render()
        self.assertIn('Unsubscribe or change your email preferences', optional['html_body'])
        mandatory = render_email(
            types.EVENT_CANCELLED, build_message(types.EVENT_CANCELLED, self.alice, self.event, {'refund': 'failed'})
        )
        self.assertIn('always sent', mandatory['html_body'])
        self.assertIn('could not refund your payment automatically', mandatory['body'])
        self.assertEqual(mandatory['attachments'], [])

    def test_every_type_renders(self):
        booking = Booking.objects.create(owner=self.alice, event=self.event, status=Booking.Status.CONFIRMED)
        booking_seat = BookingSeat.objects.create(booking=booking, seat=self.seat(row=4, col=1), price=10)
        data = {
            'registration': self.registration,
            'amount': Decimal('10.00'),
            'currency': 'usd',
            'reason': 'why',
            'attendee': 'bob',
            'note': 'ok',
            'changes': [('Date', 'old', 'new')],
            'refund': 'refunded',
            'minutes': 30,
            'booking': booking,
            'booking_seat': booking_seat,
            'owner_name': 'Alice',
            'subject': 'Doors open at 6',
            'text': 'See you there.',
            'title': 'Two-factor authentication is on',
            'body': 'You turned on email codes.',
        }
        for key in types.TYPES:
            with self.subTest(key):
                email = render_email(key, build_message(key, self.alice, self.event, data))
                self.assertTrue(email['subject'])
                self.assertIn('<html', email['html_body'])
                self.assertIn('EventHub', email['html_body'])


# ───────────────────────── email job ─────────────────────────


class SendEmailJobTests(TestCase):
    def attachment(self, **overrides):
        item = {
            'filename': 'ticket.png',
            'mimetype': 'image/png',
            'content_b64': base64.b64encode(PNG_MAGIC + b'rest').decode(),
            'cid': 'ticket-qr-0',
        }
        item.update(overrides)
        return item

    def test_the_worker_sends_html_with_an_inline_image(self):
        enqueue_email(
            'Your ticket',
            'plain text',
            'a@example.com',
            html_body='<p><img src="cid:ticket-qr-0"></p>',
            attachments=[
                self.attachment(),
                self.attachment(cid='', filename='receipt.pdf', mimetype='application/pdf'),
            ],
            headers={'List-Unsubscribe': '<https://x/profile>'},
        )
        self.assertEqual(run_due_jobs(), 1)
        self.assertEqual(Job.objects.get().status, Job.STATUS_DONE)
        sent = mail.outbox[0]
        self.assertEqual((sent.subject, sent.body, sent.to), ('Your ticket', 'plain text', ['a@example.com']))
        self.assertEqual(sent.alternatives[0][1], 'text/html')
        self.assertEqual(sent.extra_headers['List-Unsubscribe'], '<https://x/profile>')
        raw = sent.message().as_string()
        self.assertIn('multipart/related', raw)
        self.assertIn('Content-ID: <ticket-qr-0>', raw)
        self.assertIn('filename="receipt.pdf"', raw)

    def test_plain_jobs_still_work(self):
        enqueue_email('Hi', 'body', ['a@example.com'])
        self.assertEqual(
            Job.objects.get().payload, {'subject': 'Hi', 'body': 'body', 'to': ['a@example.com'], 'from_email': None}
        )
        run_due_jobs()
        self.assertEqual((mail.outbox[0].body, mail.outbox[0].alternatives), ('body', []))

    def test_unsafe_attachments_and_headers_are_refused(self):
        cases = [
            [self.attachment(mimetype='text/html')],
            [self.attachment(content_b64='not base64!')],
            [self.attachment(content_b64=base64.b64encode(b'x' * (256 * 1024 + 1)).decode())],
            [self.attachment(cid='bad cid>')],
            [self.attachment(cid='x', mimetype='application/pdf')],
            [self.attachment()] * 11,
        ]
        for attachments in cases:
            with self.subTest(attachments=str(attachments)[:80]), self.assertRaises(PermanentJobError):
                build_email_message(subject='s', body='b', to=['a@example.com'], attachments=attachments)
        with self.assertRaises(PermanentJobError):
            build_email_message(subject='s', body='b', to=['a@x.com'], headers={'List-Unsubscribe': 'a\r\nBcc: x'})

    def test_only_allowed_headers_pass_and_filenames_are_sanitised(self):
        message = build_email_message(
            subject='s\r\nBcc: evil@example.com',
            body='b',
            to=['a@example.com'],
            headers={'Bcc': 'evil@example.com', 'List-Unsubscribe': '<https://x>'},
            attachments=[self.attachment(cid='', filename='../../etc/passwd.png')],
        )
        self.assertEqual(message.extra_headers, {'List-Unsubscribe': '<https://x>'})
        self.assertEqual(message.bcc, [])
        self.assertNotIn('\n', message.subject)
        self.assertEqual(message.attachments[0][0], 'etc_passwd.png')

    def test_a_malformed_job_fails_permanently_without_retries(self):
        Job.objects.create(
            kind='send_email',
            payload={'subject': 's', 'body': 'b', 'to': ['a@example.com'], 'attachments': [{'mimetype': 'text/x'}]},
        )
        run_due_jobs()
        job = Job.objects.get()
        self.assertEqual((job.status, job.attempts), (Job.STATUS_FAILED, 1))
        self.assertEqual(mail.outbox, [])


# ───────────────────────── triggers ─────────────────────────


class TriggerTests(WorldMixin, TestCase):
    def setUp(self):
        self.make_world()

    def test_free_registration_sends_the_e_ticket(self):
        from events.services import register_for_event

        registration = register_for_event(user=self.alice, event=self.event)
        self.assertEqual(registration.status, 'confirmed')
        self.assertNotified(self.alice, types.REGISTRATION_CONFIRMED)
        self.assertEqual(len(email_jobs(self.alice).get().payload['attachments']), 1)

    def test_a_paid_registration_is_not_confirmed_until_paid(self):
        from events.services import register_for_event

        paid = self.make_event(price=Decimal('25.00'), title='Paid show')
        register_for_event(user=self.alice, event=paid)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(email_jobs().exists())

    def test_a_refund_notifies_the_buyer(self):
        from payments.models import Payment
        from payments.services import refund_payment

        registration = self.confirmed(self.alice)
        payment = Payment.objects.create(
            registration=registration, amount=Decimal('25.00'), currency='usd', status='completed', provider='mock'
        )
        refund_payment(payment=payment, amount='10.00', reason='Partial goodwill refund')
        self.assertNotified(self.alice, types.PAYMENT_REFUNDED)
        self.assertIn('10.00 USD', email_jobs(self.alice).get().payload['body'])

    def test_refund_request_flow(self):
        from events.models import RefundRequest
        from events.services import request_refund, resolve_refund_request
        from payments.models import Payment

        registration = self.confirmed(self.alice)
        Payment.objects.create(
            registration=registration, amount=Decimal('25.00'), currency='usd', status='completed', provider='mock'
        )
        request = request_refund(user=self.alice, event=self.event, reason='Sick')
        self.assertNotified(self.organizer, types.REFUND_REQUESTED)

        resolve_refund_request(refund_request=request, actor=self.organizer, approve=False, note='Too late')
        self.assertNotified(self.alice, types.REFUND_REJECTED)

        RefundRequest.objects.filter(pk=request.pk).update(status=RefundRequest.STATUS_PENDING)
        resolve_refund_request(refund_request=request, actor=self.organizer, approve=True)
        # One "approved" notice, not a second "refund issued" one.
        self.assertEqual(Notification.objects.filter(user=self.alice, type=types.REFUND_APPROVED).count(), 1)
        self.assertFalse(Notification.objects.filter(user=self.alice, type=types.PAYMENT_REFUNDED).exists())
        self.assertEqual(email_jobs(self.alice).count(), 2)

    def test_a_date_or_venue_change_notifies_ticket_holders_once(self):
        from events.services import update_event

        self.confirmed(self.alice)
        Registration.objects.create(user=self.bob, event=self.event, status='cancelled')
        new_date = self.event.date + timedelta(days=1)
        update_event(event=self.event, validated_data={'date': new_date, 'location': 'Arena'})
        self.assertNotified(self.alice, types.EVENT_UPDATED)
        self.assertFalse(Notification.objects.filter(user=self.bob).exists())
        body = email_jobs(self.alice).get().payload['body']
        self.assertIn('Arena (was Palace of Schoolchildren)', body)

        update_event(event=self.event, validated_data={'description': 'Better talks'})
        self.assertEqual(Notification.objects.filter(type=types.EVENT_UPDATED).count(), 1)

    def test_changes_to_an_unpublished_event_notify_nobody(self):
        from events.services import update_event

        self.confirmed(self.alice)
        Event.objects.filter(pk=self.event.pk).update(status='draft')
        self.event.refresh_from_db()
        update_event(event=self.event, validated_data={'location': 'Arena'})
        self.assertFalse(Notification.objects.exists())

    def test_cancelling_an_event_notifies_every_holder_once(self):
        from events.services import cancel_event

        self.confirmed(self.alice)
        carol = User.objects.create_user('carol', 'carol@example.com', 'password123')
        booking = Booking.objects.create(
            owner=self.bob, event=self.event, status=Booking.Status.CONFIRMED, amount_paid=Decimal('0')
        )
        BookingSeat.objects.create(booking=booking, seat=self.seat(row=2, col=2), claimed_by=carol)

        result = cancel_event(event=self.event, actor=self.organizer)
        self.assertEqual(result['notified'], 3)
        for user in (self.alice, self.bob, carol):
            self.assertNotified(user, types.EVENT_CANCELLED)
        self.assertFalse(Notification.objects.filter(type=types.PAYMENT_REFUNDED).exists())

    def test_a_waitlist_offer_notifies_the_next_in_line(self):
        from events.waitlist import promote_waitlist

        WaitlistEntry.objects.create(user=self.alice, event=self.event)
        self.assertEqual(promote_waitlist(self.event), 1)
        self.assertNotified(self.alice, types.SEAT_AVAILABLE)
        self.assertIn('30 minutes', email_jobs(self.alice).get().payload['body'])

    def test_group_booking_confirmed_and_claimed(self):
        booking = Booking.objects.create(owner=self.alice, event=self.event, status=Booking.Status.HOLDING)
        early = BookingSeat.objects.create(booking=booking, seat=self.seat(row=1, col=1), price=10, claimed_by=self.bob)
        later = BookingSeat.objects.create(booking=booking, seat=self.seat(row=1, col=2), price=10)

        confirm_booking(booking, amount_paid=Decimal('20.00'))
        self.assertNotified(self.alice, types.GROUP_BOOKING_CONFIRMED)
        self.assertEqual(len(email_jobs(self.alice).get().payload['attachments']), 2)
        # Bob claimed while the booking was on hold: his ticket comes now.
        self.assertNotified(self.bob, types.GROUP_BOOKING_CLAIMED)
        self.assertIn(str(early.ticket_uuid)[:8].upper(), email_jobs(self.bob).get().payload['body'])

        carol = User.objects.create_user('carol', 'carol@example.com', 'password123')
        claim_seat(booking=booking, seat_id=later.seat_id, attendee_name='Carol', user=carol)
        self.assertNotified(carol, types.GROUP_BOOKING_CLAIMED)
        # Renaming her own seat is not a new claim.
        claim_seat(booking=booking, seat_id=later.seat_id, attendee_name='Carol K.', user=carol)
        self.assertNotified(carol, types.GROUP_BOOKING_CLAIMED)

    def test_organizer_messages_respect_preferences(self):
        from events.messaging import broadcast_to_attendees

        self.confirmed(self.alice)
        self.confirmed(self.bob)
        NotificationPreference.objects.create(user=self.bob, email_disabled=[types.ORGANIZER_MESSAGE])
        result = broadcast_to_attendees(event=self.event, subject='Doors', body='Doors open at 6.')
        self.assertEqual(result, {'recipients': 2, 'notified': 2, 'emailed': 1, 'email_enabled': True})
        self.assertNotified(self.alice, types.ORGANIZER_MESSAGE)
        self.assertNotified(self.bob, types.ORGANIZER_MESSAGE, emails=0)


# ───────────────────────── Freedom Pay triggers ─────────────────────────


@override_settings(**FP_SETTINGS)
class FreedomPayTriggerTests(FixturesMixin, APITestCase):
    """The KZT purchase path end to end, through the fake gateway."""

    def setUp(self):
        cache.clear()
        self.make_world()
        self.gateway = FakeGateway()
        patcher = patch('payments.providers.freedompay.requests.post', self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)

    def opened(self):
        self.client.force_authenticate(user=self.buyer)
        response = self.client.post(f'/api/v1/payments/create-checkout/{self.registration.pk}/')
        self.assertEqual(response.status_code, 200, response.data)
        payment = Payment.objects.get(pk=response.data['payment_id'])
        return payment, payment.provider_session_id

    def notify(self, payment_id, order_id, **kw):
        self.client.force_authenticate(user=None)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                CALLBACK_PATH,
                data=callback_form(payment_id, order_id, **kw),
                content_type='application/x-www-form-urlencoded',
            )
        self.assertEqual(response.status_code, 200)
        return response

    def test_a_kzt_purchase_emails_the_e_ticket(self):
        payment, pid = self.opened()
        self.gateway.pay(pid)
        self.notify(pid, payment.pk)
        self.assertEqual(Notification.objects.filter(user=self.buyer, type=types.TICKET_PURCHASED).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.buyer).count(), 1)
        job = email_jobs(self.buyer).get()
        self.assertIn('5000.00 KZT', job.payload['body'])
        self.assertEqual(job.payload['attachments'][0]['cid'], 'ticket-qr-0')
        # A repeated callback changes nothing.
        self.notify(pid, payment.pk, salt='again1')
        self.assertEqual(email_jobs(self.buyer).count(), 1)

    def test_a_declined_payment_notifies_payment_failed(self):
        payment, pid = self.opened()
        self.notify(pid, payment.pk, result='0')
        self.assertEqual(Notification.objects.filter(user=self.buyer, type=types.PAYMENT_FAILED).count(), 1)
        self.assertEqual(email_jobs(self.buyer).count(), 1)

    def test_a_late_payment_is_reported_then_its_refund(self):
        from events.services import cancel_registration

        payment, pid = self.opened()
        cancel_registration(registration=self.registration)
        self.gateway.pay(pid)
        self.notify(pid, payment.pk)
        self.assertEqual(Notification.objects.filter(user=self.buyer, type=types.PAYMENT_FAILED).count(), 1)
        refunded = Notification.objects.filter(user=self.buyer, type=types.PAYMENT_REFUNDED)
        self.assertEqual(refunded.count(), 1)
        self.assertIn('5000.00 KZT', refunded.get().body)
        self.assertEqual(email_jobs(self.buyer).count(), 2)


# ───────────────────────── reminders ─────────────────────────


class ReminderTests(WorldMixin, TestCase):
    def setUp(self):
        self.make_world()
        self.soon = self.make_event(days=0, title='Tomorrow show')
        self.soon.date = timezone.now() + timedelta(hours=20)
        self.soon.save(update_fields=['date'])
        self.confirmed(self.alice, event=self.soon)
        self.confirmed(self.bob, event=self.event)  # two weeks away
        Registration.objects.create(user=self.organizer, event=self.soon, status='cancelled')

    def test_reminders_are_sent_once(self):
        self.assertEqual(send_due_reminders(), 1)
        self.assertEqual(send_due_reminders(), 0)
        self.assertNotified(self.alice, types.EVENT_REMINDER)
        self.assertFalse(Notification.objects.filter(user__in=[self.bob, self.organizer]).exists())
        self.assertEqual(SentReminder.objects.get().event, self.soon)

    def test_the_command_is_idempotent(self):
        from io import StringIO

        from django.core.management import call_command

        first, second = StringIO(), StringIO()
        call_command('send_event_reminders', stdout=first)
        call_command('send_event_reminders', stdout=second)
        self.assertIn('Sent 1 event reminder(s).', first.getvalue())
        self.assertIn('Sent 0 event reminder(s).', second.getvalue())
        self.assertEqual(email_jobs(self.alice).count(), 1)

    def test_the_worker_maintenance_pass_sends_them(self):
        from django.core.management import call_command

        call_command('run_maintenance')
        call_command('run_maintenance')
        self.assertNotified(self.alice, types.EVENT_REMINDER)

    def test_a_rescheduled_event_gets_a_new_reminder(self):
        send_due_reminders()
        self.soon.date += timedelta(hours=2)
        self.soon.save(update_fields=['date'])
        self.assertEqual(send_due_reminders(), 1)
        self.assertEqual(SentReminder.objects.filter(user=self.alice).count(), 2)

    def test_a_failed_notification_is_retried_on_the_next_pass(self):
        with patch('notifications.reminders.notify', return_value=None), self.assertLogs('notifications', 'WARNING'):
            self.assertEqual(send_due_reminders(), 0)
        self.assertFalse(SentReminder.objects.exists())
        self.assertEqual(send_due_reminders(), 1)

    def test_a_concurrent_pass_cannot_send_twice(self):
        from .reminders import _send_one

        # Another worker recorded the reminder after this pass read the list.
        SentReminder.objects.create(user=self.alice, event=self.soon, event_starts_at=self.soon.date)
        self.assertFalse(_send_one(self.alice, self.soon))
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(email_jobs().exists())

    def test_group_booking_holders_are_reminded(self):
        booking = Booking.objects.create(owner=self.bob, event=self.soon, status=Booking.Status.CONFIRMED)
        BookingSeat.objects.create(booking=booking, seat=self.seat(event=self.soon, row=1, col=1))
        self.assertEqual(send_due_reminders(), 2)

    def test_opted_out_users_get_the_in_app_reminder_only(self):
        NotificationPreference.objects.create(user=self.alice, email_disabled=[types.EVENT_REMINDER])
        send_due_reminders()
        self.assertNotified(self.alice, types.EVENT_REMINDER, emails=0)


# ───────────────────────── preferences API ─────────────────────────


class PreferencesApiTests(WorldMixin, APITestCase):
    URL = '/api/v1/auth/profile/notifications/'

    def setUp(self):
        self.make_world()

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(self.client.patch(self.URL, {'email': {}}, format='json').status_code, 401)

    def test_defaults_are_all_on(self):
        self.client.force_authenticate(self.alice)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email_address'], 'alice@example.com')
        rows = {row['type']: row for row in response.data['types']}
        self.assertTrue(all(row['email_enabled'] for row in rows.values()))
        self.assertFalse(rows[types.EVENT_CANCELLED]['email_optional'])
        self.assertTrue(rows[types.EVENT_REMINDER]['email_optional'])
        self.assertNotIn(types.REVIEW_REMINDER, rows)  # in-app only

    def test_switching_an_email_off_and_on(self):
        self.client.force_authenticate(self.alice)
        response = self.client.patch(self.URL, {'email': {types.EVENT_REMINDER: False}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        rows = {row['type']: row for row in response.data['types']}
        self.assertFalse(rows[types.EVENT_REMINDER]['email_enabled'])
        self.assertTrue(rows[types.TICKET_PURCHASED]['email_enabled'])
        self.assertEqual(NotificationPreference.objects.get(user=self.alice).email_disabled, [types.EVENT_REMINDER])

        self.client.patch(self.URL, {'email': {types.EVENT_REMINDER: True}}, format='json')
        self.assertEqual(NotificationPreference.objects.get(user=self.alice).email_disabled, [])

    def test_preferences_are_per_user(self):
        self.client.force_authenticate(self.alice)
        self.client.patch(self.URL, {'email': {types.SEAT_AVAILABLE: False}}, format='json')
        self.client.force_authenticate(self.bob)
        rows = {row['type']: row for row in self.client.get(self.URL).data['types']}
        self.assertTrue(rows[types.SEAT_AVAILABLE]['email_enabled'])
        self.assertFalse(NotificationPreference.objects.filter(user=self.bob).exists())

    def test_mandatory_unknown_and_malformed_values_are_rejected(self):
        self.client.force_authenticate(self.alice)
        for body in (
            {'email': {types.EVENT_CANCELLED: False}},
            {'email': {types.PAYMENT_REFUNDED: False}},
            {'email': {'password_reset': False}},
            {'email': {types.EVENT_REMINDER: 'maybe'}},
            {'email': 'off'},
            {},
        ):
            with self.subTest(body=body):
                self.assertEqual(self.client.patch(self.URL, body, format='json').status_code, 400)
        self.assertFalse(NotificationPreference.objects.exists())

    def test_the_legacy_alias_serves_it_too(self):
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.get('/api/auth/profile/notifications/').status_code, 200)


# ───────────────────────── security emails ─────────────────────────


class SecurityEmailTests(WorldMixin, APITestCase):
    """Sign-up and password-reset codes are not notifications: they ignore
    the preferences and are always emailed."""

    def setUp(self):
        self.make_world()
        NotificationPreference.objects.create(user=self.alice, email_disabled=list(types.EMAIL_OPTIONAL_TYPES))

    def test_password_reset_end_to_end_ignores_preferences(self):
        from accounts.models import PasswordResetCode

        response = self.client.post('/api/v1/auth/password-reset/request/', {'identifier': 'alice'}, format='json')
        self.assertEqual(response.status_code, 200)
        run_due_jobs()
        self.assertEqual(len(mail.outbox), 1)
        code = PasswordResetCode.objects.get(user=self.alice).code
        self.assertIn(code, mail.outbox[0].body)

        response = self.client.post(
            '/api/v1/auth/password-reset/verify/', {'identifier': 'alice', 'code': code}, format='json'
        )
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(
            '/api/v1/auth/password-reset/confirm/',
            {
                'reset_token': response.data['reset_token'],
                'new_password': 'N3w-Passw0rd!x',
                'new_password2': 'N3w-Passw0rd!x',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.check_password('N3w-Passw0rd!x'))

    def test_no_reset_code_for_an_account_without_an_address(self):
        User.objects.filter(pk=self.bob.pk).update(email='')
        response = self.client.post('/api/v1/auth/password-reset/request/', {'identifier': 'bob'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(email_jobs().exists())

    def test_sign_up_code_is_emailed(self):
        response = self.client.post('/api/v1/auth/register/send-code/', {'email': 'new@example.com'}, format='json')
        self.assertEqual(response.status_code, 200)
        run_due_jobs()
        self.assertEqual(mail.outbox[0].to, ['new@example.com'])
        self.assertIn('verification code', mail.outbox[0].body)
