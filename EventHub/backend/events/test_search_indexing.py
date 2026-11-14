"""Search indexing jobs are queued only when they can run.

Regression: the slim image (INSTALL_SEMANTIC_SEARCH=0, used by CI and the
e2e stack) queued an `index_event` job for every saved event; each failed
permanently ("sentence-transformers is not installed") and the
`outbox_jobs_stuck` data check reported them as undelivered work.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from events.models import Category
from events.search import index_event_async
from jobs.models import Job

FIND_SPEC = 'events.search.importlib.util.find_spec'


class IndexEventQueueTests(APITestCase):
    def setUp(self):
        self.organizer = User.objects.create_user('org', 'org@example.com', 'Str0ng-pass!')
        self.organizer.profile.role = 'organizer'
        self.organizer.profile.save()
        self.category = Category.objects.create(name='Music')

    def create_event(self):
        self.client.force_authenticate(self.organizer)
        response = self.client.post(
            '/api/v1/events/',
            {
                'title': 'Indexed?',
                'description': 'd',
                'date': (timezone.now() + timedelta(days=3)).isoformat(),
                'location': 'Almaty',
                'max_participants': 10,
                'price': '10.00',
                'category_id': self.category.id,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['id']

    def index_jobs(self):
        return Job.objects.filter(kind='index_event')

    def test_slim_image_queues_no_index_job(self):
        with patch(FIND_SPEC, return_value=None):
            self.create_event()
        self.assertFalse(self.index_jobs().exists())

    def test_full_image_queues_one_index_job(self):
        with patch(FIND_SPEC, return_value=object()):
            event_id = self.create_event()
        self.assertEqual([job.payload for job in self.index_jobs()], [{'event_id': event_id}])

    def test_direct_call_follows_the_same_rule(self):
        event = type('E', (), {'pk': 42})()
        with patch(FIND_SPEC, return_value=None):
            index_event_async(event)
        self.assertEqual(self.index_jobs().count(), 0)
