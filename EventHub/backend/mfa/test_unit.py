"""2FA building blocks: TOTP window and replay, encryption at rest, recovery
codes, the role policy and the production start-up guard."""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

from . import crypto, recovery, totp
from .conf import DEV_ENCRYPTION_KEY, production_problems
from .models import RecoveryCode, TOTPDevice
from .policy import mfa_enabled, mfa_required_for, token_satisfies_policy
from .testing import enroll_totp, mfa_access_token


class TOTPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', 'Str0ng-pass!')
        self.secret = enroll_totp(self.user)
        self.device = TOTPDevice.objects.get(user=self.user)

    def code(self, offset=0):
        return totp.code_for_step(self.secret, totp.current_step() + offset)

    def test_the_current_and_adjacent_steps_are_accepted(self):
        for offset in (-1, 0, 1):
            with self.subTest(offset=offset):
                self.device.last_used_step = None
                self.device.save()
                self.assertTrue(totp.verify(self.device, self.code(offset)))

    def test_codes_two_steps_away_are_refused(self):
        self.assertFalse(totp.verify(self.device, self.code(-2)))
        self.assertFalse(totp.verify(self.device, self.code(2)))

    def test_a_code_is_accepted_only_once(self):
        code = self.code()
        self.assertTrue(totp.verify(self.device, code))
        self.device.refresh_from_db()
        self.assertFalse(totp.verify(self.device, code))

    def test_an_older_code_is_refused_after_a_newer_one(self):
        self.assertTrue(totp.verify(self.device, self.code(1)))
        self.device.refresh_from_db()
        self.assertFalse(totp.verify(self.device, self.code(0)))
        self.assertFalse(totp.verify(self.device, self.code(-1)))

    def test_malformed_codes_are_refused(self):
        for bad in ('', '12345', '1234567', 'abcdef', None):
            self.assertFalse(totp.verify(self.device, bad))

    def test_spaces_in_a_typed_code_are_ignored(self):
        code = self.code()
        self.assertTrue(totp.verify(self.device, f'{code[:3]} {code[3:]}'))

    def test_matches_rfc6238_reference_values(self):
        # RFC 6238 appendix B, SHA-1 secret "12345678901234567890", 8 digits
        # there; the last 6 digits are what a 6-digit generator shows.
        import base64

        secret = base64.b32encode(b'12345678901234567890').decode()
        self.assertEqual(totp.code_for_step(secret, 59 // 30), '287082')
        self.assertEqual(totp.code_for_step(secret, 1111111109 // 30), '081804')


class EncryptionAtRestTests(TestCase):
    def test_the_database_never_holds_the_plain_secret(self):
        user = User.objects.create_user('bob', 'bob@example.com', 'Str0ng-pass!')
        secret = enroll_totp(user)
        with connection.cursor() as cursor:
            cursor.execute('SELECT encrypted_secret FROM mfa_totpdevice WHERE user_id = %s', [user.pk])
            stored = cursor.fetchone()[0]
        self.assertNotIn(secret, stored)
        self.assertEqual(crypto.decrypt_secret(stored), secret)

    def test_a_secret_encrypted_with_another_key_cannot_be_read(self):
        with override_settings(MFA_ENCRYPTION_KEYS=['another-key-entirely-another-key-entirely']):
            token = crypto.encrypt_secret('JBSWY3DPEHPK3PXP')
        with self.assertRaises(crypto.SecretDecryptionError):
            crypto.decrypt_secret(token)

    def test_key_rotation_reencrypts_on_use(self):
        old_key, new_key = 'old-key-old-key-old-key-old-key-old', 'new-key-new-key-new-key-new-key-new'
        user = User.objects.create_user('carol', 'carol@example.com', 'Str0ng-pass!')
        with override_settings(MFA_ENCRYPTION_KEYS=[old_key]):
            secret = enroll_totp(user)
        with override_settings(MFA_ENCRYPTION_KEYS=[new_key, old_key]):
            device = TOTPDevice.objects.get(user=user)
            self.assertTrue(crypto.needs_rotation(device.encrypted_secret))
            self.assertTrue(totp.verify(device, totp.code_for_step(secret, totp.current_step())))
            device.refresh_from_db()
            self.assertFalse(crypto.needs_rotation(device.encrypted_secret))
        with override_settings(MFA_ENCRYPTION_KEYS=[new_key]):
            self.assertEqual(crypto.decrypt_secret(TOTPDevice.objects.get(user=user).encrypted_secret), secret)


class RecoveryCodeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dave', 'dave@example.com', 'Str0ng-pass!')

    def test_ten_codes_are_stored_hashed(self):
        codes = recovery.regenerate(self.user)
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        stored = list(RecoveryCode.objects.filter(user=self.user).values_list('code_hash', flat=True))
        self.assertEqual(len(stored), 10)
        for code in codes:
            self.assertRegex(code, r'^[a-z2-9]{4}(-[a-z2-9]{4}){3}$')
            self.assertFalse(any(recovery.normalize(code) in h or code in h for h in stored))

    def test_a_code_works_once(self):
        code = recovery.regenerate(self.user)[3]
        self.assertTrue(recovery.use(self.user, code))
        self.assertFalse(recovery.use(self.user, code))
        self.assertEqual(recovery.remaining(self.user), 9)

    def test_typing_variations_are_accepted(self):
        code = recovery.regenerate(self.user)[0]
        self.assertTrue(recovery.use(self.user, f'  {code.upper().replace("-", " ")} '))

    def test_regenerating_invalidates_the_old_codes(self):
        old = recovery.regenerate(self.user)
        recovery.regenerate(self.user)
        self.assertFalse(recovery.use(self.user, old[0]))

    def test_another_users_code_does_not_work(self):
        other = User.objects.create_user('eve', 'eve@example.com', 'Str0ng-pass!')
        code = recovery.regenerate(other)[0]
        recovery.regenerate(self.user)
        self.assertFalse(recovery.use(self.user, code))


class PolicyTests(TestCase):
    def make(self, name, role='attendee', **flags):
        user = User.objects.create_user(name, f'{name}@example.com', 'Str0ng-pass!', **flags)
        user.profile.role = role
        user.profile.save()
        return user

    def test_default_roles(self):
        self.assertEqual(settings.MFA_REQUIRED_ROLES, ['organizer', 'staff', 'superuser'])
        self.assertTrue(mfa_required_for(self.make('o', role='organizer')))
        self.assertTrue(mfa_required_for(self.make('s', is_staff=True)))
        self.assertTrue(mfa_required_for(self.make('su', is_superuser=True)))
        self.assertFalse(mfa_required_for(self.make('a')))

    @override_settings(MFA_REQUIRED_ROLES=[])
    def test_enforcement_can_be_switched_off(self):
        self.assertFalse(mfa_required_for(self.make('o', role='organizer')))

    @override_settings(MFA_REQUIRED_ROLES=['attendee'])
    def test_attendees_can_be_included(self):
        self.assertTrue(mfa_required_for(self.make('a')))

    def test_token_policy(self):
        attendee, organizer = self.make('a'), self.make('o', role='organizer')
        plain = mfa_access_token(attendee)
        del plain['mfa_at']
        self.assertTrue(token_satisfies_policy(attendee, plain))
        self.assertFalse(token_satisfies_policy(organizer, plain))
        self.assertTrue(token_satisfies_policy(organizer, mfa_access_token(organizer)))
        enroll_totp(attendee)  # opted in: a password-only token is no longer enough
        self.assertTrue(mfa_enabled(attendee))
        self.assertFalse(token_satisfies_policy(attendee, plain))

    def test_the_enabled_cache_follows_factor_changes(self):
        user = self.make('c')
        self.assertFalse(mfa_enabled(user))
        enroll_totp(user)
        self.assertTrue(mfa_enabled(user))
        TOTPDevice.objects.filter(user=user).delete()
        self.assertFalse(mfa_enabled(user))


class ProductionGuardTests(SimpleTestCase):
    def test_problems(self):
        ok = {'rp_id': 'eventhub.example', 'origins': ['https://eventhub.example']}
        self.assertEqual(production_problems(encryption_keys=['x' * 40], **ok), [])
        self.assertIn('MFA_ENCRYPTION_KEY must be set', production_problems(encryption_keys=[], **ok)[0])
        self.assertIn(
            'MFA_ENCRYPTION_KEY must be set', production_problems(encryption_keys=[DEV_ENCRYPTION_KEY], **ok)[0]
        )
        self.assertIn('at least 32', production_problems(encryption_keys=['short'], **ok)[0])
        bad_rp = production_problems(encryption_keys=['x' * 40], rp_id='https://x.example', origins=['https://x'])
        self.assertIn('WEBAUTHN_RP_ID', bad_rp[0])

    def load_settings(self, **env):
        environment = {key: value for key, value in os.environ.items() if not key.startswith('MFA_')}
        environment.update(
            {
                'DJANGO_SETTINGS_MODULE': 'eventhub_backend.settings',
                'DJANGO_SECRET_KEY': 'test-only-secret-key-for-the-guard',
                'DJANGO_ALLOWED_HOSTS': 'eventhub.example',
                'EMAIL_HOST_USER': 'mailer',
                'EMAIL_HOST_PASSWORD': 'mail-password',
                'DJANGO_DEBUG': '0',
                'PAYMENT_PROVIDERS_ENABLED': 'stripe',
                'STRIPE_SECRET_KEY': 'sk_live_x',
                'STRIPE_WEBHOOK_SECRET': 'whsec_x',
                'PAYMENTS_MOCK_MODE': '',
                'STRIPE_MOCK_MODE': '',
                'UNLEASH_ENABLED': '0',
            }
        )
        environment.pop('EMAIL_BACKEND', None)
        environment.update(env)
        done = subprocess.run(
            [sys.executable, '-c', 'from django.conf import settings; print(len(settings.MFA_ENCRYPTION_KEYS))'],
            cwd=Path(settings.BASE_DIR),
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return done.returncode, done.stdout.strip(), done.stderr

    def test_production_refuses_to_start_without_a_key(self):
        code, _, stderr = self.load_settings()
        self.assertNotEqual(code, 0)
        self.assertIn('MFA_ENCRYPTION_KEY must be set', stderr)

    def test_production_starts_with_a_key(self):
        code, out, stderr = self.load_settings(MFA_ENCRYPTION_KEY='a-real-production-key-of-48-chars-abcdefghijklm')
        self.assertEqual(code, 0, stderr)
        self.assertEqual(out, '1')

    def test_debug_falls_back_to_the_dev_key(self):
        code, _, stderr = self.load_settings(DJANGO_DEBUG='1')
        self.assertEqual(code, 0, stderr)

    def test_unknown_roles_are_refused(self):
        code, _, stderr = self.load_settings(DJANGO_DEBUG='1', MFA_REQUIRED_ROLES='organizer,admins')
        self.assertNotEqual(code, 0)
        self.assertIn('MFA_REQUIRED_ROLES lists unknown roles: admins', stderr)
