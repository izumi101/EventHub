"""The settings an operator is told to set in `.env` must reach the backend.

docker-compose.yml lists the backend's environment explicitly, so a variable
documented in docs/SECURITY_2FA.md but missing there is silently ignored:
MFA_ENCRYPTION_KEY could not be set at all, and with DJANGO_DEBUG=0 the
backend then refuses to start. Runs where the repository is checked out (CI,
a developer's machine); skipped inside the backend image, which has no
compose file.
"""

import re
import unittest

import yaml
from django.conf import settings
from django.test import SimpleTestCase

REPO = settings.BASE_DIR.parent
COMPOSE = REPO / 'docker-compose.yml'
SECURITY_DOC = REPO / 'docs' / 'SECURITY_2FA.md'


def documented_2fa_settings() -> set[str]:
    """First column of the settings table in the 2FA operator guide."""
    names = set()
    for line in SECURITY_DOC.read_text(encoding='utf-8').splitlines():
        if line.startswith('| `'):
            names.update(re.findall(r'`([A-Z][A-Z0-9_]+)`', line.split('|')[1]))
    return names


@unittest.skipUnless(COMPOSE.exists() and SECURITY_DOC.exists(), 'needs the repository checkout')
class ComposeEnvironmentTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        services = yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))['services']
        cls.env = {name: set(services[name]['environment']) for name in ('backend', 'worker')}

    def test_the_guide_lists_settings(self):
        self.assertGreaterEqual(documented_2fa_settings(), {'MFA_ENCRYPTION_KEY', 'WEBAUTHN_ORIGINS'})

    def test_every_documented_2fa_setting_reaches_backend_and_worker(self):
        for service, env in self.env.items():
            with self.subTest(service=service):
                self.assertEqual(documented_2fa_settings() - env, set())

    def test_rate_limit_overrides_reach_the_backend(self):
        self.assertIn('DJANGO_THROTTLE_RATES', self.env['backend'])
