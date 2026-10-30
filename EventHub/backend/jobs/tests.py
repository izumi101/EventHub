from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from events.models import Event, Webhook, WebhookDelivery
from events.webhooks import fire
from jobs.handlers import enqueue_email
from jobs.models import Job
from jobs.queue import enqueue, run_due_jobs


class QueueTests(TestCase):
    def test_job_is_rolled_back_with_its_transaction(self):
        # Outbox: no email for a change that never committed.
        try:
            with transaction.atomic():
                enqueue_email('Hi', 'body', 'a@example.com')
                raise RuntimeError('business logic failed')
        except RuntimeError:
            pass
        self.assertFalse(Job.objects.exists())

    def test_email_job_sends_mail(self):
        enqueue_email('Hello', 'body', 'a@example.com')
        self.assertEqual(run_due_jobs(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Job.objects.get().status, Job.STATUS_DONE)

    def test_failures_are_retried_with_backoff_then_given_up(self):
        job = enqueue('send_email', {'subject': 's', 'body': 'b', 'to': ['a@example.com']}, max_attempts=2)
        with patch('jobs.handlers.django_send_mail', side_effect=OSError('smtp down')):
            run_due_jobs()
            job.refresh_from_db()
            self.assertEqual((job.status, job.attempts), (Job.STATUS_PENDING, 1))
            self.assertGreater(job.run_after, timezone.now())
            self.assertIn('smtp down', job.last_error)
            self.assertEqual(run_due_jobs(), 0)  # not due yet

            Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
            run_due_jobs()
        job.refresh_from_db()
        self.assertEqual((job.status, job.attempts), (Job.STATUS_FAILED, 2))

    def test_job_of_a_crashed_worker_is_picked_up_after_its_lease(self):
        job = enqueue_email('Hi', 'body', 'a@example.com')
        Job.objects.filter(pk=job.pk).update(
            status=Job.STATUS_RUNNING, run_after=timezone.now() - timedelta(seconds=1),
        )
        self.assertEqual(run_due_jobs(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_DONE)

    def test_job_that_keeps_killing_the_worker_is_given_up(self):
        job = enqueue_email('Hi', 'body', 'a@example.com')
        Job.objects.filter(pk=job.pk).update(
            status=Job.STATUS_RUNNING, attempts=job.max_attempts,
            run_after=timezone.now() - timedelta(seconds=1),
        )
        self.assertEqual(run_due_jobs(), 0)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertEqual(len(mail.outbox), 0)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            enqueue('rm_rf', {})


class WebhookJobTests(TestCase):
    def setUp(self):
        organizer = User.objects.create_user('org', 'org@example.com', 'Str0ng-pass!')
        self.event = Event.objects.create(
            title='E', description='d', organizer=organizer, location='x',
            date=timezone.now() + timedelta(days=2), status='published',
        )

    def hook(self, url):
        return Webhook.objects.create(event=self.event, url=url, secret='s3cret',
                                      triggers=['ticket_sold'])

    def test_failed_delivery_is_retried(self):
        hook = self.hook('https://hooks.example.com/eventhub')
        fire(self.event, 'ticket_sold', {'x': 1})
        with patch('events.webhooks._post', return_value=503):
            run_due_jobs()
        job = Job.objects.get(kind='deliver_webhook')
        self.assertEqual(job.status, Job.STATUS_PENDING)
        Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
        with patch('events.webhooks._post', return_value=200) as post:
            run_due_jobs()
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_DONE)
        # Signed body is exactly what was queued.
        self.assertIn('"trigger": "ticket_sold"', post.call_args.args[1].decode())
        self.assertEqual(list(WebhookDelivery.objects.filter(webhook=hook).values_list('success', flat=True)
                              .order_by('created_at')), [False, True])

    def test_ssrf_blocked_delivery_is_not_retried(self):
        self.hook('http://127.0.0.1:8000/admin/')
        fire(self.event, 'ticket_sold', {})
        run_due_jobs()
        job = Job.objects.get(kind='deliver_webhook')
        self.assertEqual((job.status, job.attempts), (Job.STATUS_FAILED, 1))

    def test_worker_command_runs_jobs_and_maintenance(self):
        enqueue_email('Hi', 'body', 'a@example.com')
        call_command('run_worker', '--once')
        self.assertEqual(len(mail.outbox), 1)
