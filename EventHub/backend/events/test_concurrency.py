"""Regression tests that must run *outside* a wrapping transaction.

APITestCase wraps every test in a transaction, which hid the fact that
register_for_event used select_for_update() in autocommit mode (500 on
PostgreSQL). These tests use TransactionTestCase and real threads with their
own DB connections, like concurrent requests in production.
"""

import threading
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from events.models import Event, PromoCode, Registration
from events.services import check_in_registration, register_for_event


def _run_concurrently(fn, args_list):
    barrier = threading.Barrier(len(args_list))
    results = [None] * len(args_list)

    def worker(i, args):
        try:
            barrier.wait()
            results[i] = ('ok', fn(*args))
        except Exception as exc:  # noqa: BLE001 — the test inspects it
            results[i] = ('error', exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, a)) for i, a in enumerate(args_list)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


class RegistrationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.organizer = User.objects.create_user('org', 'org@example.com', 'pw-Strong-123')
        self.organizer.profile.role = 'organizer'
        self.organizer.profile.save()
        self.buyers = [User.objects.create_user(f'buyer{i}', f'b{i}@example.com', 'pw-Strong-123') for i in range(2)]
        self.event = Event.objects.create(
            title='Last seat',
            description='d',
            organizer=self.organizer,
            date=timezone.now() + timedelta(days=3),
            location='Hall',
            price=10,
            max_participants=1,
            status='published',
        )

    def test_register_endpoint_works_without_outer_transaction(self):
        # K1: used to raise TransactionManagementError → HTTP 500.
        client = APIClient()
        client.force_authenticate(self.buyers[0])
        response = client.post(f'/api/v1/events/{self.event.id}/register/', {}, format='json')
        self.assertEqual(response.status_code, 201, response.content)

    def test_two_buyers_cannot_both_take_the_last_spot(self):
        results = _run_concurrently(
            lambda user: register_for_event(user=user, event=self.event),
            [(u,) for u in self.buyers],
        )
        self.assertEqual(sum(1 for kind, _ in results if kind == 'ok'), 1, results)
        self.assertEqual(
            Registration.objects.filter(event=self.event).exclude(status='cancelled').count(),
            1,
        )

    def test_single_use_promo_code_cannot_be_used_twice_concurrently(self):
        self.event.max_participants = 10
        self.event.save()
        PromoCode.objects.create(event=self.event, code='ONCE', discount_type='percent', discount_value=50, max_uses=1)
        results = _run_concurrently(
            lambda user: register_for_event(user=user, event=self.event, promo_code='once'),
            [(u,) for u in self.buyers],
        )
        self.assertEqual(sum(1 for kind, _ in results if kind == 'ok'), 1, results)
        self.assertEqual(PromoCode.objects.get(code='ONCE').times_used, 1)

    def test_same_ticket_scanned_at_two_gates_is_admitted_once(self):
        reg = Registration.objects.create(user=self.buyers[0], event=self.event, status='confirmed')
        results = _run_concurrently(
            lambda: check_in_registration(registration=reg, actor=self.organizer),
            [(), ()],
        )
        used_flags = sorted(r[1][1] for r in results if r[0] == 'ok')
        self.assertEqual(used_flags, [False, True], results)
