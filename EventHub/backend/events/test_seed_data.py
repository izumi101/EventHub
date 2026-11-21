"""seed_data: the admin password reaches the log only when it was generated.

Regression: with DJANGO_SEED_ADMIN_PASSWORD set, the configured password
was printed to the backend log as well (`.env.example` promises it is
printed only when none is set).
"""

import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from events.models import Event


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


@override_settings(DEBUG=False)
class SeedDataDemoDeploymentTests(TestCase):
    """DJANGO_DEBUG=0: only with --i-know-this-is-a-demo and a demo password
    of the deployment's own (common/demo_seed.py)."""

    SEED_ENV = {'DJANGO_SEED_ADMIN_PASSWORD', 'DJANGO_SEED_DEMO_PASSWORD', 'DJANGO_SEED_MFA_TOTP_SECRET'}

    def seed(self, *args, **env):
        out = StringIO()
        clean = {k: v for k, v in os.environ.items() if k not in self.SEED_ENV}
        with patch.dict(os.environ, {**clean, **env}, clear=True):
            call_command('seed_data', '--noinput', *args, stdout=out)
        return out.getvalue()

    def test_refuses_without_the_flag(self):
        with self.assertRaisesMessage(CommandError, '--i-know-this-is-a-demo'):
            self.seed(DJANGO_SEED_DEMO_PASSWORD='a-long-demo-password')
        self.assertFalse(User.objects.exists())

    def test_refuses_without_a_strong_demo_password(self):
        for password in ('', 'short', 'password123'):
            with self.subTest(password=password), self.assertRaisesMessage(CommandError, 'DJANGO_SEED_DEMO_PASSWORD'):
                self.seed('--i-know-this-is-a-demo', DJANGO_SEED_DEMO_PASSWORD=password)
        self.assertFalse(User.objects.exists())

    def test_refuses_the_public_test_totp_secret(self):
        with self.assertRaisesMessage(CommandError, 'DJANGO_SEED_MFA_TOTP_SECRET'):
            self.seed(
                '--i-know-this-is-a-demo',
                DJANGO_SEED_DEMO_PASSWORD='a-long-demo-password',
                DJANGO_SEED_MFA_TOTP_SECRET='JBSWY3DPEHPK3PXP',
            )

    def test_accounts_get_the_deployment_password_which_is_never_printed(self):
        output = self.seed(
            '--i-know-this-is-a-demo',
            '--accounts-only',
            DJANGO_SEED_DEMO_PASSWORD='a-long-demo-password',
            DJANGO_SEED_ADMIN_PASSWORD='configured-Secret-42',
        )
        self.assertNotIn('a-long-demo-password', output)
        self.assertNotIn('password123', output)
        for username in ('organizer', 'attendee'):
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password('a-long-demo-password'))
            self.assertFalse(user.check_password('password123'))
        self.assertTrue(User.objects.get(username='admin').check_password('configured-Secret-42'))
        self.assertFalse(Event.objects.exists())
