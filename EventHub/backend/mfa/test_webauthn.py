"""WebAuthn / passkeys: registration and assertion verified by py_webauthn
against a software authenticator (P-256, "none" attestation)."""

import hashlib
import json
import os

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.test import override_settings
from rest_framework_simplejwt.tokens import AccessToken
from webauthn.helpers import bytes_to_base64url

from .models import WebAuthnCredential
from .test_login import LOGIN, PROFILE, MFABase
from .testing import authenticate_with_recent_mfa, enroll_totp

ORIGIN = 'http://localhost:4200'
RP_ID = 'localhost'


class SoftAuthenticator:
    """Just enough of a FIDO2 authenticator for the server-side checks."""

    def __init__(self, *, rp_id=RP_ID, origin=ORIGIN, counter=0):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.rp_id = rp_id
        self.origin = origin
        self.counter = counter

    @property
    def id(self):
        return bytes_to_base64url(self.credential_id)

    def _cose_public_key(self):
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, 'big'), -3: numbers.y.to_bytes(32, 'big')})

    def _client_data(self, kind, challenge, origin=None):
        return json.dumps(
            {'type': kind, 'challenge': challenge, 'origin': origin or self.origin, 'crossOrigin': False}
        ).encode()

    def _rp_hash(self):
        return hashlib.sha256(self.rp_id.encode()).digest()

    def register(self, options, *, origin=None):
        client_data = self._client_data('webauthn.create', options['challenge'], origin)
        auth_data = (
            self._rp_hash()
            + bytes([0x41])  # user present + attested credential data
            + self.counter.to_bytes(4, 'big')
            + bytes(16)  # AAGUID
            + len(self.credential_id).to_bytes(2, 'big')
            + self.credential_id
            + self._cose_public_key()
        )
        attestation = cbor2.dumps({'fmt': 'none', 'attStmt': {}, 'authData': auth_data})
        return {
            'id': self.id,
            'rawId': self.id,
            'type': 'public-key',
            'response': {
                'clientDataJSON': bytes_to_base64url(client_data),
                'attestationObject': bytes_to_base64url(attestation),
                'transports': ['internal', 'hybrid'],
            },
            'clientExtensionResults': {},
        }

    def sign(self, options, *, counter=None, origin=None):
        self.counter = self.counter + 1 if counter is None else counter
        client_data = self._client_data('webauthn.get', options['challenge'], origin)
        auth_data = self._rp_hash() + bytes([0x01]) + self.counter.to_bytes(4, 'big')
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            'id': self.id,
            'rawId': self.id,
            'type': 'public-key',
            'response': {
                'clientDataJSON': bytes_to_base64url(client_data),
                'authenticatorData': bytes_to_base64url(auth_data),
                'signature': bytes_to_base64url(signature),
                'userHandle': None,
            },
            'clientExtensionResults': {},
        }


@override_settings(WEBAUTHN_RP_ID=RP_ID, WEBAUTHN_ORIGINS=[ORIGIN])
class PasskeyTests(MFABase):
    OPTIONS = '/api/v1/auth/mfa/webauthn/register/options/'
    REGISTER = '/api/v1/auth/mfa/webauthn/register/verify/'

    def setUp(self):
        super().setUp()
        self.user = self.make_user('pat', role='organizer')
        self.authenticator = SoftAuthenticator()

    def register(self, authenticator=None, name='MacBook Touch ID', **kw):
        authenticator = authenticator or self.authenticator
        options = self.client.post(self.OPTIONS, {'name': name}).data
        return self.client.post(
            self.REGISTER, {'name': name, 'credential': authenticator.register(options, **kw)}, format='json'
        )

    def enroll_with_enrollment_token(self):
        self.bearer(self.login(self.user).data['enrollment_token'])
        response = self.register()
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials()
        return response

    def test_registration_options_carry_the_rp_and_exclude_known_keys(self):
        self.bearer(self.login(self.user).data['enrollment_token'])
        options = self.client.post(self.OPTIONS, {'name': 'Key'}).data
        self.assertEqual(options['rp'], {'name': 'EventHub', 'id': RP_ID})
        self.assertEqual(options['user']['name'], 'pat')
        self.assertNotEqual(options['user']['id'], str(self.user.pk))
        self.assertEqual(options['attestation'], 'none')

    def test_a_passkey_as_first_factor_finishes_enrollment(self):
        response = self.enroll_with_enrollment_token()
        self.assertEqual(len(response.data['recovery_codes']), 10)
        self.assertIn('hwk', AccessToken(response.data['tokens']['access'])['amr'])
        credential = WebAuthnCredential.objects.get(user=self.user)
        self.assertEqual((credential.name, credential.credential_id), ('MacBook Touch ID', self.authenticator.id))
        self.assertEqual(credential.transports, ['internal', 'hybrid'])

    def test_a_wrong_origin_is_refused(self):
        self.bearer(self.login(self.user).data['enrollment_token'])
        response = self.register(origin='https://evil.example')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WebAuthnCredential.objects.exists())

    def test_a_wrong_rp_id_is_refused(self):
        self.bearer(self.login(self.user).data['enrollment_token'])
        response = self.register(SoftAuthenticator(rp_id='evil.example'))
        self.assertEqual(response.status_code, 400)

    def test_a_registration_challenge_is_single_use(self):
        self.bearer(self.login(self.user).data['enrollment_token'])
        options = self.client.post(self.OPTIONS, {'name': 'Key'}).data
        credential = self.authenticator.register(options)
        self.assertEqual(self.client.post(self.REGISTER, {'credential': credential}, format='json').status_code, 200)
        authenticate_with_recent_mfa(self.client, self.user)
        self.assertEqual(self.client.post(self.REGISTER, {'credential': credential}, format='json').status_code, 400)

    def passkey_login(self, authenticator=None, **kw):
        challenge = self.login(self.user).data['challenge_token']
        options = self.client.post('/api/v1/auth/mfa/login/webauthn/options/', {'challenge_token': challenge}).data
        self.assertEqual(options['rpId'], RP_ID)
        self.assertEqual([c['id'] for c in options['allowCredentials']], [self.authenticator.id])
        assertion = (authenticator or self.authenticator).sign(options, **kw)
        return self.client.post(
            '/api/v1/auth/mfa/login/verify/',
            {'challenge_token': challenge, 'method': 'webauthn', 'credential': assertion},
            format='json',
        )

    def test_login_with_a_passkey(self):
        self.enroll_with_enrollment_token()
        response = self.passkey_login()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('hwk', AccessToken(response.data['tokens']['access'])['amr'])
        self.assertEqual(WebAuthnCredential.objects.get().sign_count, 1)

    def test_a_signature_from_another_key_is_refused(self):
        self.enroll_with_enrollment_token()
        impostor = SoftAuthenticator()
        impostor.credential_id = self.authenticator.credential_id
        self.assertEqual(self.passkey_login(impostor).status_code, 400)

    def test_a_counter_going_backwards_is_refused_as_a_possible_clone(self):
        self.enroll_with_enrollment_token()
        self.assertEqual(self.passkey_login(counter=10).status_code, 200)
        with self.assertLogs('mfa', level='WARNING') as logs:
            response = self.passkey_login(counter=5)
        self.assertEqual(response.status_code, 400)
        self.assertIn('mfa.passkey_clone_suspected', '\n'.join(logs.output))
        self.assertEqual(WebAuthnCredential.objects.get().sign_count, 10)

    def test_an_assertion_cannot_be_replayed(self):
        self.enroll_with_enrollment_token()
        challenge = self.login(self.user).data['challenge_token']
        options = self.client.post('/api/v1/auth/mfa/login/webauthn/options/', {'challenge_token': challenge}).data
        assertion = self.authenticator.sign(options)
        body = {'challenge_token': challenge, 'method': 'webauthn', 'credential': assertion}
        self.assertEqual(self.client.post('/api/v1/auth/mfa/login/verify/', body, format='json').status_code, 200)
        other = self.login(self.user).data['challenge_token']
        body['challenge_token'] = other
        self.assertEqual(self.client.post('/api/v1/auth/mfa/login/verify/', body, format='json').status_code, 400)

    def test_step_up_with_a_passkey(self):
        self.enroll_with_enrollment_token()
        authenticate_with_recent_mfa(self.client, self.user, age_seconds=3600)
        self.assertEqual(self.client.post('/api/v1/auth/mfa/recovery-codes/regenerate/').status_code, 403)
        options = self.client.post('/api/v1/auth/mfa/step-up/webauthn/options/').data
        response = self.client.post(
            '/api/v1/auth/mfa/step-up/',
            {'method': 'webauthn', 'credential': self.authenticator.sign(options)},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(None)
        self.bearer(response.data['access'])
        self.assertEqual(self.client.post('/api/v1/auth/mfa/recovery-codes/regenerate/').status_code, 200)

    def test_adding_a_second_passkey_needs_step_up_and_removal_too(self):
        self.enroll_with_enrollment_token()
        enroll_totp(self.user)
        authenticate_with_recent_mfa(self.client, self.user, age_seconds=3600)
        refused = self.client.post(self.OPTIONS, {'name': 'YubiKey'})
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'mfa_step_up_required'))
        authenticate_with_recent_mfa(self.client, self.user)
        self.assertEqual(self.register(SoftAuthenticator(), name='YubiKey').status_code, 200)
        self.assertEqual(WebAuthnCredential.objects.filter(user=self.user).count(), 2)

        first = WebAuthnCredential.objects.get(name='MacBook Touch ID')
        authenticate_with_recent_mfa(self.client, self.user, age_seconds=3600)
        self.assertEqual(self.client.delete(f'/api/v1/auth/mfa/webauthn/credentials/{first.pk}/').status_code, 403)
        authenticate_with_recent_mfa(self.client, self.user)
        response = self.client.delete(f'/api/v1/auth/mfa/webauthn/credentials/{first.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p['name'] for p in response.data['passkeys']], ['YubiKey'])

    def test_another_users_passkey_cannot_be_removed(self):
        self.enroll_with_enrollment_token()
        other = self.make_user('mallory')
        authenticate_with_recent_mfa(self.client, other)
        enroll_totp(other)
        key = WebAuthnCredential.objects.get(user=self.user)
        self.assertEqual(self.client.delete(f'/api/v1/auth/mfa/webauthn/credentials/{key.pk}/').status_code, 404)

    def test_profile_works_with_the_passkey_session(self):
        tokens = self.enroll_with_enrollment_token().data['tokens']
        self.bearer(tokens['access'])
        self.assertEqual(self.client.get(PROFILE).status_code, 200)
        self.client.credentials()
        self.assertTrue(self.client.post(LOGIN, {'username': 'pat', 'password': self.password}).data['mfa_required'])
