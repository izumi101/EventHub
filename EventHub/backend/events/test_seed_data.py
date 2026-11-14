"""seed_data: the admin password reaches the log only when it was generated.

Regression: with DJANGO_SEED_ADMIN_PASSWORD set, the configured password
was printed to the backend log as well (`.env.example` promises it is
printed only when none is set).
"""

import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings


@override_settings(DEBUG=True)
class SeedAdminPasswordTests(TestCase):
    def seed(self, **env):
        out = StringIO()
        without_password = {k: v for k, v in os.environ.items() if k != 'DJANGO_SEED_ADMIN_PASSWORD'}
        with patch.dict(os.environ, {**without_password, **env}, clear=True):
            call_command('seed_data', '--noinput', stdout=out)
        return out.getvalue()

    def test_configured_password_is_not_printed(self):
        output = self.seed(DJANGO_SEED_ADMIN_PASSWORD='configured-Secret-42')
        self.assertNotIn('configured-Secret-42', output)
        self.assertIn('DJANGO_SEED_ADMIN_PASSWORD', output)
        self.assertTrue(User.objects.get(username='admin').check_password('configured-Secret-42'))

    def test_generated_password_is_printed_once(self):
        output = self.seed()
        line = next(line for line in output.splitlines() if line.startswith('Admin login: admin / '))
        password = line.removeprefix('Admin login: admin / ')
        self.assertTrue(User.objects.get(username='admin').check_password(password))
