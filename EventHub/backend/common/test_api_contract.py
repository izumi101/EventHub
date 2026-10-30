"""The API contract: versioned URLs, the deprecated alias, and the committed
OpenAPI schema staying in step with the code."""

import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

SCHEMA_FILE = Path(settings.BASE_DIR) / 'openapi.yaml'
REGENERATE = 'python manage.py spectacular --file openapi.yaml --validate --fail-on-warn'


class VersioningTests(TestCase):
    def test_names_resolve_to_v1(self):
        self.assertEqual(reverse('event-list'), '/api/v1/events/')

    def test_v1_is_not_deprecated(self):
        response = self.client.get('/api/v1/events/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Deprecation', response.headers)

    def test_unversioned_alias_still_works_and_says_where_to_go(self):
        response = self.client.get('/api/events/?search=x')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['Deprecation'].startswith('@'))
        self.assertIn('GMT', response.headers['Sunset'])
        self.assertEqual(response.headers['Link'], '</api/v1/events/>; rel="successor-version"')

    def test_fixed_addresses_are_not_deprecated(self):
        for path in ('/api/health/', '/api/payments/webhook/'):
            response = self.client.post(path) if 'webhook' in path else self.client.get(path)
            self.assertNotIn('Deprecation', response.headers, path)


class SchemaTests(TestCase):
    def test_schema_is_served(self):
        response = self.client.get('/api/v1/schema/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'openapi:', response.content)

    def test_committed_schema_matches_the_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp) / 'openapi.yaml'
            call_command('spectacular', '--file', str(generated), '--validate', '--fail-on-warn')
            self.assertEqual(
                generated.read_text(),
                SCHEMA_FILE.read_text(),
                f'openapi.yaml is out of date; regenerate it in EventHub/backend: {REGENERATE}',
            )
