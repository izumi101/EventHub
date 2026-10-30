"""Regression tests for the issues listed in REVIEW.md (events app)."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from events.models import (
    CheckInList,
    Event,
    EventStaff,
    PromoCode,
    Registration,
    Review,
    TicketType,
)
from payments.models import Payment


class Base(APITestCase):
    def setUp(self):
        self.organizer = self.make_user('organizer', role='organizer')
        self.attendee = self.make_user('attendee')
        self.other = self.make_user('other')
        self.event = self.make_event()

    @staticmethod
    def make_user(name, role='attendee'):
        user = User.objects.create_user(name, f'{name}@example.com', 'Str0ng-pass!')
        user.profile.role = role
        user.profile.save()
        return user

    def make_event(self, **kw):
        data = dict(
            title='Conf',
            description='d',
            organizer=self.organizer,
            date=timezone.now() + timedelta(days=5),
            location='Hall',
            price=Decimal('100.00'),
            max_participants=10,
            status='published',
        )
        data.update(kw)
        return Event.objects.create(**data)

    def register(self, user=None, event=None, **data):
        self.client.force_authenticate(user or self.attendee)
        return self.client.post(f'/api/v1/events/{(event or self.event).id}/register/', data, format='json')


class CheckInListTests(Base):
    def setUp(self):
        super().setUp()
        self.lst = CheckInList.objects.create(event=self.event, name='Main', is_default=True)
        self.url = f'/api/v1/checkin-lists/{self.lst.id}/check-in/'

    def scan(self, reg, action='check_in', user=None):
        self.client.force_authenticate(user or self.organizer)
        return self.client.post(self.url, {'ticket_uuid': str(reg.ticket_uuid), 'action': action}, format='json')

    def test_pending_and_cancelled_tickets_are_refused(self):
        # K6: list check-in used to admit unpaid and cancelled tickets.
        pending = Registration.objects.create(user=self.attendee, event=self.event, status='pending')
        self.assertEqual(self.scan(pending).status_code, 400)
        pending.status = 'cancelled'
        pending.save()
        self.assertEqual(self.scan(pending).status_code, 400)
        pending.refresh_from_db()
        self.assertFalse(pending.is_checked_in)

    def test_confirmed_ticket_is_admitted_once(self):
        reg = Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        first = self.scan(reg)
        self.assertEqual(first.data['status'], 'success')
        second = self.scan(reg)
        self.assertEqual(second.data['status'], 'used')
        reg.refresh_from_db()
        self.assertTrue(reg.is_checked_in)

    def test_unknown_action_is_rejected(self):
        reg = Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        self.assertEqual(self.scan(reg, action='teleport').status_code, 400)

    def test_lists_are_not_readable_by_strangers(self):
        # Important #1: GET used to skip the permission check (IDOR).
        self.client.force_authenticate(self.other)
        response = self.client.get(f'/api/v1/events/{self.event.id}/checkin-lists/')
        self.assertEqual(response.status_code, 403)

    def test_check_in_staff_can_scan_but_not_edit_lists(self):
        # Important #10: the check-in role used to be useless for lists.
        EventStaff.objects.create(event=self.event, user=self.other, role=EventStaff.ROLE_CHECK_IN)
        reg = Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        self.assertEqual(self.scan(reg, user=self.other).status_code, 200)
        response = self.client.post(f'/api/v1/events/{self.event.id}/checkin-lists/', {'name': 'VIP'})
        self.assertEqual(response.status_code, 403)


class PermissionTests(Base):
    def test_co_organizer_cannot_appoint_more_staff(self):
        EventStaff.objects.create(event=self.event, user=self.other, role=EventStaff.ROLE_CO_ORGANIZER)
        self.client.force_authenticate(self.other)
        response = self.client.post(
            f'/api/v1/events/{self.event.id}/staff/', {'invite_username': 'attendee', 'role': 'co_organizer'}
        )
        self.assertEqual(response.status_code, 403)

    def test_co_organizer_can_edit_but_not_delete(self):
        EventStaff.objects.create(event=self.event, user=self.other, role=EventStaff.ROLE_CO_ORGANIZER)
        self.client.force_authenticate(self.other)
        url = f'/api/v1/events/{self.event.id}/'
        self.assertEqual(self.client.patch(url, {'title': 'New'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 403)

    def test_event_with_paid_tickets_cannot_be_deleted(self):
        # Important #9: deleting used to cascade away the payment records.
        reg = Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        Payment.objects.create(registration=reg, amount=100, status='completed')
        self.client.force_authenticate(self.organizer)
        response = self.client.delete(f'/api/v1/events/{self.event.id}/')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Payment.objects.filter(registration=reg).exists())

    def test_online_link_is_only_for_ticket_holders(self):
        # Important #2.
        self.event.is_online = True
        self.event.online_link = 'https://meet.example.com/secret'
        self.event.save()
        url = f'/api/v1/events/{self.event.id}/'
        self.assertEqual(self.client.get(url).data['online_link'], '')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).data['online_link'], '')
        Registration.objects.create(user=self.other, event=self.event, status='confirmed')
        self.assertEqual(self.client.get(url).data['online_link'], 'https://meet.example.com/secret')

    def test_staff_create_without_username_is_a_400(self):
        # Important #19: used to be an AttributeError → 500.
        self.client.force_authenticate(self.organizer)
        response = self.client.post(f'/api/v1/events/{self.event.id}/staff/', {'role': 'check_in'})
        self.assertEqual(response.status_code, 400)


class MoneyTests(Base):
    def test_promo_use_is_reserved_and_released(self):
        # Important #12: max_uses was checked without reserving the use.
        PromoCode.objects.create(event=self.event, code='HALF', discount_type='percent', discount_value=50, max_uses=1)
        self.assertEqual(self.register(promo_code='half').status_code, 201)
        self.assertEqual(PromoCode.objects.get().times_used, 1)
        response = self.register(user=self.other, promo_code='HALF')
        self.assertEqual(response.status_code, 400)
        # Releasing the unpaid hold gives the use back.
        self.client.force_authenticate(self.attendee)
        self.client.post(f'/api/v1/events/{self.event.id}/cancel/')
        self.assertEqual(PromoCode.objects.get().times_used, 0)

    def test_tier_price_is_locked_at_registration(self):
        # Important #13: only GA prices used to be locked.
        from events.billing import registration_amount

        tier = TicketType.objects.create(event=self.event, name='VIP', kind='paid', price=Decimal('80'))
        response = self.register(ticket_type_id=tier.id)
        self.assertEqual(response.status_code, 201)
        tier.price = Decimal('500')
        tier.save()
        reg = Registration.objects.get(id=response.data['id'])
        self.assertEqual(registration_amount(reg), Decimal('80.00'))

    def test_invalid_donation_amount_is_a_400(self):
        TicketType.objects.create(event=self.event, name='Pay what you want', kind='donation', price=5)
        tier = TicketType.objects.get()
        response = self.register(ticket_type_id=tier.id, donation_amount='abc')
        self.assertEqual(response.status_code, 400)

    def test_cancel_event_voids_free_tickets_and_survives_a_failed_refund(self):
        # Important #16.
        paid = Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        Payment.objects.create(registration=paid, amount=100, status='completed')
        free = Registration.objects.create(user=self.other, event=self.event, status='confirmed')
        with patch('payments.services.refund_payment', side_effect=RuntimeError('stripe down')):
            self.client.force_authenticate(self.organizer)
            response = self.client.post(f'/api/v1/events/{self.event.id}/cancel-event/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['refund_failed'], 1)
        free.refresh_from_db()
        self.assertEqual(free.status, 'cancelled')
        # The failed refund is not reported to the attendee as refunded.
        note = paid.user.notifications.get(type='event_cancelled')
        self.assertNotIn('has been refunded', note.body)


class AnalyticsTests(Base):
    def test_full_refunds_are_reported(self):
        from events.analytics import event_analytics

        kept = Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        Payment.objects.create(registration=kept, amount=100, status='completed')
        gone = Registration.objects.create(user=self.other, event=self.event, status='cancelled')
        Payment.objects.create(registration=gone, amount=100, refunded_amount=100, status='refunded')
        kpis = event_analytics(self.event)['kpis']
        self.assertEqual((kpis['gross_revenue'], kpis['refunded'], kpis['net_revenue']), (200.0, 100.0, 100.0))


class AdminDashboardTests(Base):
    def test_revenue_is_per_currency_and_net_of_refunds(self):
        kzt_event = self.make_event(title='KZT', currency='KZT')
        usd = Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        Payment.objects.create(registration=usd, amount=100, refunded_amount=40, currency='usd', status='completed')
        kzt = Registration.objects.create(user=self.other, event=kzt_event, status='confirmed')
        Payment.objects.create(registration=kzt, amount=5000, currency='kzt', status='completed')
        admin = User.objects.create_superuser('root', 'root@example.com', 'Str0ng-pass!')
        self.client.force_authenticate(admin)
        data = self.client.get('/api/v1/admin-dashboard/').data
        self.assertEqual(
            data['revenue_by_currency'],
            [
                {'currency': 'KZT', 'amount': '5000.00'},
                {'currency': 'USD', 'amount': '60.00'},
            ],
        )


class ValidationTests(Base):
    def test_duplicate_promo_code_is_a_400_not_a_500(self):
        self.client.force_authenticate(self.organizer)
        url = f'/api/v1/events/{self.event.id}/promo-codes/'
        data = {'code': 'save10', 'discount_type': 'percent', 'discount_value': 10}
        self.assertEqual(self.client.post(url, data).status_code, 201)
        data['code'] = 'SAVE10'
        self.assertEqual(self.client.post(url, data).status_code, 400)

    def test_second_review_is_a_400(self):
        past = self.make_event(date=timezone.now() - timedelta(days=1))
        Registration.objects.create(user=self.attendee, event=past, status='confirmed')
        Review.objects.create(user=self.attendee, event=past, rating=5)
        self.client.force_authenticate(self.attendee)
        response = self.client.post(f'/api/v1/events/{past.id}/reviews/', {'rating': 4})
        self.assertEqual(response.status_code, 400)

    def test_event_fields_are_validated(self):
        # Important #20.
        self.client.force_authenticate(self.organizer)
        base = {
            'title': 'X',
            'description': 'd',
            'location': 'L',
            'category_id': None,
            'date': (timezone.now() + timedelta(days=3)).isoformat(),
        }
        from events.models import Category

        base['category_id'] = Category.objects.create(name='Tech').id
        for bad in (
            {'price': -1},
            {'tax_percent': 150},
            {'currency': 'dollars'},
            {'end_date': (timezone.now() + timedelta(days=1)).isoformat()},
        ):
            response = self.client.post('/api/v1/events/', {**base, **bad}, format='json')
            self.assertEqual(response.status_code, 400, bad)

    def test_capacity_cannot_drop_below_tickets_sold(self):
        for i in range(3):
            Registration.objects.create(user=self.make_user(f'u{i}'), event=self.event, status='confirmed')
        self.client.force_authenticate(self.organizer)
        response = self.client.patch(f'/api/v1/events/{self.event.id}/', {'max_participants': 2}, format='json')
        self.assertEqual(response.status_code, 400)


class BookingRuleTests(Base):
    def test_attendee_cannot_book_a_draft_event(self):
        # Important #11: group bookings skipped the event-state checks.
        draft = self.make_event(status='draft')
        self.client.force_authenticate(self.organizer)
        self.client.post(f'/api/v1/events/{draft.id}/seat-map/create/', {'rows': 2, 'cols': 2}, format='json')
        seat_ids = list(draft.seat_map.seats.values_list('id', flat=True)[:2])
        self.client.force_authenticate(self.attendee)
        response = self.client.post('/api/v1/bookings/', {'event': draft.id, 'seat_ids': seat_ids}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_waiting_room_refusal_carries_a_stable_code(self):
        # The SPA branches on `code`, not on the human-readable message.
        with (
            patch('events.queue.is_queue_active', return_value=True),
            patch('events.queue.validate_queue_token', return_value=False),
        ):
            response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'QUEUE_REQUIRED')
        self.assertNotEqual(response.data['error'], 'QUEUE_REQUIRED')
        self.assertFalse(Registration.objects.filter(event=self.event).exists())


class ExportTests(Base):
    def test_formula_injection_is_neutralised(self):
        # Important #3.
        from openpyxl import load_workbook

        evil = self.make_user('evil')
        evil.first_name = '=HYPERLINK("http://evil.example","click")'
        evil.save()
        Registration.objects.create(user=evil, event=self.event, status='confirmed')
        self.client.force_authenticate(self.organizer)
        response = self.client.get(f'/api/v1/events/{self.event.id}/export-attendees/')
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertTrue(sheet['A2'].value.startswith("'="))


class QueryCountTests(Base):
    def test_event_list_query_count_does_not_grow_with_events(self):
        # Important #22: ~10 queries per event card before.
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get('/api/v1/events/').status_code, 200)
            return len(ctx.captured_queries)

        few = count()
        for i in range(8):
            ev = self.make_event(title=f'E{i}')
            TicketType.objects.create(event=ev, name='GA', kind='paid', price=10)
        self.assertEqual(count(), few)

    def test_my_registrations_query_count_does_not_grow_with_tickets(self):
        self.client.force_authenticate(self.attendee)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get('/api/v1/my-registrations/').status_code, 200)
            return len(ctx.captured_queries)

        Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        one = count()
        for i in range(5):
            Registration.objects.create(user=self.attendee, event=self.make_event(title=f'R{i}'), status='confirmed')
        self.assertEqual(count(), one)


class WaitlistTests(Base):
    def test_cancelling_an_event_does_not_offer_spots_to_the_waitlist(self):
        from events.models import WaitlistEntry

        self.event.max_participants = 1
        self.event.save()
        Registration.objects.create(user=self.attendee, event=self.event, status='confirmed')
        WaitlistEntry.objects.create(user=self.other, event=self.event)
        self.client.force_authenticate(self.organizer)
        self.client.post(f'/api/v1/events/{self.event.id}/cancel-event/')
        self.assertEqual(WaitlistEntry.objects.get(user=self.other).status, 'waiting')
        self.assertFalse(self.other.notifications.filter(type='seat_available').exists())


class AttendeeListTests(Base):
    def test_plain_list_by_default_paginated_on_request(self):
        for i in range(3):
            Registration.objects.create(user=self.make_user(f'p{i}'), event=self.event, status='confirmed')
        self.client.force_authenticate(self.organizer)
        url = f'/api/v1/events/{self.event.id}/registrations/'
        plain = self.client.get(url).data
        self.assertEqual(len(plain), 3)
        self.assertNotIn('event', plain[0])  # not re-serialised per row
        page = self.client.get(url, {'page': 1, 'page_size': 2}).data
        self.assertEqual((page['count'], len(page['results'])), (3, 2))


class CommandTests(Base):
    def test_run_maintenance_releases_holds_and_completes_past_events(self):
        # Important #23: this work moved out of GET requests into a scheduler.
        promo = PromoCode.objects.create(
            event=self.event, code='P', discount_type='percent', discount_value=10, times_used=1
        )
        stale = Registration.objects.create(
            user=self.attendee,
            event=self.event,
            status='pending',
            promo_code=promo,
            seat_held_until=timezone.now() - timedelta(minutes=1),
        )
        past = self.make_event(date=timezone.now() - timedelta(days=2), end_date=timezone.now() - timedelta(days=1))
        call_command('run_maintenance')
        stale.refresh_from_db()
        past.refresh_from_db()
        promo.refresh_from_db()
        self.assertEqual(stale.status, 'cancelled')
        self.assertEqual(promo.times_used, 0)
        self.assertEqual(past.status, 'completed')

    def test_seat_map_read_does_not_write(self):
        Registration.objects.create(
            user=self.attendee,
            event=self.event,
            status='pending',
            seat_held_until=timezone.now() - timedelta(minutes=1),
        )
        self.client.force_authenticate(self.organizer)
        self.client.post(f'/api/v1/events/{self.event.id}/seat-map/create/', {'rows': 1, 'cols': 1}, format='json')
        self.client.force_authenticate(None)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(f'/api/v1/events/{self.event.id}/seat_map/')
        writes = [
            q for q in ctx.captured_queries if q['sql'].lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE'))
        ]
        self.assertEqual(writes, [])

    def test_generate_seat_maps_force_needs_an_event(self):
        # Important #27: --force used to wipe every seat map of every event.
        with self.assertRaises(CommandError):
            call_command('generate_seat_maps', '--force')
