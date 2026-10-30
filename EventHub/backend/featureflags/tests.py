"""Feature flags: registry, safe defaults, the Unleash client wrapper, the
DRF permission and the flags endpoint.

The real UnleashClient is exercised without a server: either against a
closed port (Unleash down) or with flag state bootstrapped into its cache,
which runs the actual evaluation engine on our context.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import warnings
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import yaml
from django.conf import settings
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIClient, force_authenticate
from rest_framework.views import APIView
from UnleashClient.constants import FEATURES_URL

from common.choices import RoleChoices

from . import client as flag_client
from .checks import check_flag_registry, overdue_flags
from .log_filters import RateLimitFilter
from .permissions import require_flag
from .registry import ALL_FLAGS, CLIENT_FLAGS, FLAGS_BY_KEY, Flag, Flags, registry_problems
from .service import build_context, client_flags, is_enabled, override_flags

FLAG = Flags.PAYMENTS_FREEDOMPAY
ON_BY_DEFAULT = Flag(
    key='ops.kill_switch',
    default=True,
    description='A kill switch: on unless an operator turns it off.',
    owner='platform',
    remove_by=date(2099, 1, 1),
)

# Unleash is running and configured, but nothing listens on this port.
UNLEASH_DOWN = {
    'UNLEASH_ENABLED': True,
    'UNLEASH_URL': 'http://127.0.0.1:9/api',
    'UNLEASH_API_TOKEN': '*:development.test-token',
    'UNLEASH_APP_NAME': 'eventhub-tests',
    'UNLEASH_ENVIRONMENT': 'development',
    'UNLEASH_REQUEST_TIMEOUT': 1,
    'UNLEASH_REFRESH_INTERVAL': 15,
    'UNLEASH_METRICS_INTERVAL': 60,
}


def make_user(username, role=RoleChoices.ATTENDEE, **extra):
    user = User.objects.create_user(username=username, password='Pass-12345', **extra)
    user.profile.role = role
    user.profile.save()
    return User.objects.get(pk=user.pk)


def unleash_state(*features):
    """A client-API features payload, as Unleash serves it."""
    return {'version': 2, 'features': list(features)}


def feature(name, *, enabled=True, strategies=None):
    return {
        'name': name,
        'type': 'release',
        'enabled': enabled,
        'strategies': strategies if strategies is not None else [{'name': 'default', 'parameters': {}}],
    }


def bootstrapped_cache(state):
    cache = flag_client.MemoryCache()
    cache.set(FEATURES_URL, json.dumps(state))
    cache.bootstrapped = True
    return cache


class ClientResetMixin:
    """A fresh client per test. The SDK's connection errors and our start-up
    line stay out of the test output (tests that care use assertLogs), and the
    SDK log de-duplication is forgotten so each test sees every message."""

    QUIET_LOGGERS = {'UnleashClient': logging.CRITICAL, 'featureflags.client': logging.CRITICAL}

    def setUp(self):
        super().setUp()
        for name, level in self.QUIET_LOGGERS.items():
            logger = logging.getLogger(name)
            self.addCleanup(logger.setLevel, logger.level)
            logger.setLevel(level)
        flag_client.reset_client()
        self.addCleanup(flag_client.reset_client)
        for log_filter in logging.getLogger('UnleashClient').filters:
            if isinstance(log_filter, RateLimitFilter):
                log_filter.reset()


class RegistryTests(SimpleTestCase):
    def test_declared_flags_are_valid(self):
        self.assertEqual(registry_problems(), [])
        self.assertEqual(check_flag_registry(), [])

    def test_initial_flags_are_off_until_rolled_out(self):
        self.assertIn('payments.freedompay', FLAGS_BY_KEY)
        self.assertIn('checkin.offline_scanner', FLAGS_BY_KEY)
        for flag in ALL_FLAGS:
            self.assertFalse(flag.default, flag.key)

    def test_bad_declarations_are_reported(self):
        flags = (
            Flag('Payments-New', False, 'x', 'owner', date(2099, 1, 1)),
            Flag('a.b', False, 'x', 'owner', date(2099, 1, 1)),
            Flag('a.b', False, 'x', 'owner', date(2099, 1, 1)),
            Flag('c.d', 'yes', '', 'owner', date(2099, 1, 1)),
        )
        problems = '\n'.join(registry_problems(flags))
        self.assertIn("'Payments-New' is not a valid flag key", problems)
        self.assertIn("'a.b' is declared more than once", problems)
        self.assertIn("'c.d' must have a bool default", problems)
        self.assertIn("'c.d' needs a description and an owner", problems)

    def test_overdue_flags_are_found(self):
        overdue = Flag('old.flag', False, 'x', 'owner', date(2020, 1, 1))
        self.assertEqual(overdue_flags((overdue, FLAG), today=date(2026, 1, 1)), [overdue])
        with mock.patch('featureflags.checks.ALL_FLAGS', (overdue,)):
            (warning,) = check_flag_registry()
        self.assertEqual(warning.id, 'featureflags.W001')


class SettingsTests(SimpleTestCase):
    def test_unleash_is_off_in_tests(self):
        self.assertFalse(settings.UNLEASH_ENABLED)

    def test_enabling_without_url_or_token_refuses_to_start(self):
        env = {**os.environ, 'DJANGO_DEBUG': '1', 'UNLEASH_ENABLED': '1', 'UNLEASH_URL': '', 'UNLEASH_API_TOKEN': ''}
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            cwd=settings.BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)
        self.assertIn('UNLEASH_ENABLED=1 needs UNLEASH_URL and UNLEASH_API_TOKEN', result.stderr)


class DefaultsWithoutUnleashTests(ClientResetMixin, TestCase):
    """UNLEASH_ENABLED=0 (tests, local development): no client, defaults."""

    def test_defaults_without_creating_a_client(self):
        user = make_user('anna')
        with mock.patch.object(flag_client, 'UnleashClient') as factory:
            self.assertFalse(is_enabled(FLAG, user))
            self.assertFalse(is_enabled(FLAG))
            self.assertTrue(is_enabled(ON_BY_DEFAULT, user))
        factory.assert_not_called()
        self.assertIsNone(flag_client.get_client())

    def test_flags_can_be_looked_up_by_key(self):
        self.assertFalse(is_enabled('payments.freedompay'))

    def test_unknown_flag_is_off_and_does_not_raise(self):
        with self.assertLogs('featureflags.service', 'ERROR'):
            self.assertFalse(is_enabled('no.such_flag'))


@override_settings(**UNLEASH_DOWN)
class UnleashDownTests(ClientResetMixin, TestCase):
    """The real SDK, configured, with Unleash unreachable."""

    def test_defaults_immediately_and_never_raise(self):
        user = make_user('anna')
        with (
            self.assertLogs('UnleashClient', 'WARNING') as sdk_logs,
            self.assertLogs('featureflags.client', 'WARNING') as our_logs,
        ):
            self.assertFalse(is_enabled(FLAG, user))
            self.assertTrue(is_enabled(ON_BY_DEFAULT, user))
            self.assertTrue(flag_client.wait_until_started(timeout=10))
        # The outage is visible in the log.
        self.assertTrue(any('feature fetch failed' in line for line in sdk_logs.output), sdk_logs.output)
        self.assertIn('is not answering; feature flags use their defaults', our_logs.output[0])

        client = flag_client.get_client()
        self.assertIsNotNone(client)
        self.assertTrue(client.is_initialized)  # keeps polling until Unleash is back
        self.assertFalse(is_enabled(FLAG, user))
        self.assertTrue(is_enabled(ON_BY_DEFAULT, user))
        self.assertEqual(client_flags(user), {flag.key: flag.default for flag in CLIENT_FLAGS})

    def test_malformed_url_falls_back_to_defaults(self):
        with (
            override_settings(UNLEASH_URL='not a url'),
            self.assertLogs('featureflags.client', 'ERROR'),
            self.assertLogs('UnleashClient', 'ERROR'),
        ):
            self.assertFalse(is_enabled(FLAG))
            flag_client.wait_until_started(timeout=10)
        self.assertFalse(is_enabled(FLAG))
        self.assertTrue(is_enabled(ON_BY_DEFAULT))

    def test_client_that_cannot_be_built_is_not_retried_per_lookup(self):
        with (
            mock.patch.object(flag_client, 'UnleashClient', side_effect=RuntimeError('boom')) as factory,
            self.assertLogs('featureflags.client', 'ERROR'),
        ):
            self.assertFalse(is_enabled(FLAG))
            self.assertTrue(is_enabled(ON_BY_DEFAULT))
            self.assertFalse(is_enabled(FLAG))
        self.assertEqual(factory.call_count, 1)


@override_settings(**UNLEASH_DOWN)
class UnleashEvaluationTests(ClientResetMixin, TestCase):
    """The real SDK and evaluation engine, with flag state as Unleash would
    serve it (bootstrapped: no network needed)."""

    def use_state(self, state):
        for patcher in (
            mock.patch.object(flag_client, '_make_cache', return_value=bootstrapped_cache(state)),
            # Evaluate the bootstrapped state only: no registration or polling.
            mock.patch.object(flag_client, '_initialize'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unleash_overrides_the_default_for_known_flags(self):
        self.use_state(
            unleash_state(
                feature(FLAG.key, enabled=True),
                feature(ON_BY_DEFAULT.key, enabled=False),
            )
        )
        self.assertTrue(is_enabled(FLAG))
        self.assertFalse(is_enabled(ON_BY_DEFAULT))

    def test_flags_unleash_does_not_know_use_their_default(self):
        self.use_state(unleash_state(feature('something.else')))
        self.assertFalse(is_enabled(FLAG))
        self.assertTrue(is_enabled(ON_BY_DEFAULT))

    def test_user_id_targets_individual_users(self):
        alice, bob = make_user('alice'), make_user('bob')
        self.use_state(
            unleash_state(
                feature(FLAG.key, strategies=[{'name': 'userWithId', 'parameters': {'userIds': str(alice.pk)}}])
            )
        )
        self.assertTrue(is_enabled(FLAG, alice))
        self.assertFalse(is_enabled(FLAG, bob))
        self.assertFalse(is_enabled(FLAG))  # no user, no match
        self.assertEqual(client_flags(alice)[FLAG.key], True)
        self.assertEqual(client_flags(bob)[FLAG.key], False)

    def test_role_and_environment_constraints(self):
        organizer = make_user('olga', RoleChoices.ORGANIZER)
        attendee = make_user('artur')

        def constrained(context_name, values):
            return [
                {
                    'name': 'default',
                    'parameters': {},
                    'constraints': [{'contextName': context_name, 'operator': 'IN', 'values': values}],
                }
            ]

        self.use_state(
            unleash_state(
                feature(FLAG.key, strategies=constrained('role', ['organizer'])),
                feature(Flags.CHECKIN_OFFLINE_SCANNER.key, strategies=constrained('environment', ['production'])),
            )
        )
        self.assertTrue(is_enabled(FLAG, organizer))
        self.assertFalse(is_enabled(FLAG, attendee))
        # The deployment's environment (UNLEASH_ENVIRONMENT=development) is part of the context.
        self.assertFalse(is_enabled(Flags.CHECKIN_OFFLINE_SCANNER, organizer))

    def test_gradual_rollout_is_sticky_per_user(self):
        users = [make_user(f'user{i}') for i in range(40)]
        self.use_state(
            unleash_state(
                feature(
                    FLAG.key,
                    strategies=[
                        {
                            'name': 'flexibleRollout',
                            'parameters': {'rollout': '50', 'stickiness': 'userId', 'groupId': FLAG.key},
                        }
                    ],
                )
            )
        )
        first = [is_enabled(FLAG, user) for user in users]
        self.assertEqual(first, [is_enabled(FLAG, user) for user in users])
        self.assertTrue(any(first))
        self.assertFalse(all(first))


class FakeUnleash:
    """A minimal Unleash client API on localhost: serves `state`, records
    what the SDK sent."""

    def __init__(self):
        self.state = unleash_state()
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, status, body=b''):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                fake.requests.append(('GET', self.path, dict(self.headers)))
                if self.path.startswith('/api/client/features'):
                    self._reply(200, json.dumps(fake.state).encode())
                else:
                    self._reply(404)

            def do_POST(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(length) or b'{}')
                fake.requests.append(('POST', self.path, dict(self.headers), body))
                self._reply(202)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}/api'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class LiveClientTests(ClientResetMixin, TestCase):
    """The real SDK polling a (fake) Unleash server over HTTP."""

    def setUp(self):
        super().setUp()
        self.unleash = FakeUnleash()
        self.addCleanup(self.unleash.stop)
        overrides = override_settings(
            **{**UNLEASH_DOWN, 'UNLEASH_URL': self.unleash.url, 'UNLEASH_REFRESH_INTERVAL': 1}
        )
        overrides.enable()
        self.addCleanup(overrides.disable)

    def wait_for(self, expected, user=None, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if is_enabled(FLAG, user) is expected:
                return True
            time.sleep(0.05)
        return False

    def test_follows_unleash_and_keeps_the_last_state_when_it_goes_away(self):
        self.unleash.state = unleash_state(feature(FLAG.key, enabled=True))
        user = make_user('hana')
        self.assertFalse(is_enabled(FLAG, user))  # not fetched yet: default
        self.assertTrue(flag_client.wait_until_started(timeout=10))
        self.assertTrue(is_enabled(FLAG, user))
        self.assertEqual(client_flags(user)[FLAG.key], True)

        # Switched off in Unleash: picked up by the next poll.
        self.unleash.state = unleash_state(feature(FLAG.key, enabled=False))
        self.assertTrue(self.wait_for(False, user))
        self.unleash.state = unleash_state(feature(FLAG.key, enabled=True))
        self.assertTrue(self.wait_for(True, user))

        # Unleash goes away: the last fetched state stays in force.
        self.unleash.stop()
        time.sleep(1.5)
        self.assertTrue(is_enabled(FLAG, user))

    def test_a_forked_child_polls_with_its_own_client(self):
        """What gunicorn does: fork a process whose parent already polls."""
        self.unleash.state = unleash_state(feature(FLAG.key, enabled=True))
        self.assertFalse(is_enabled(FLAG))
        self.assertTrue(flag_client.wait_until_started(timeout=10))
        self.assertTrue(is_enabled(FLAG))
        parent_client = flag_client.get_client()

        read_end, write_end = os.pipe()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)  # "multi-threaded process forked"
            pid = os.fork()
        if pid == 0:  # child: report and leave without running test cleanups
            try:
                inherited = flag_client._client is not None
                is_enabled(FLAG)  # the first lookup creates this process's client
                report = {
                    'inherited': inherited,
                    'started': flag_client.wait_until_started(timeout=10),
                    'after_fetch': is_enabled(FLAG),
                    'own_client': flag_client.get_client() is not parent_client,
                }
                os.write(write_end, json.dumps(report).encode())
            finally:
                os._exit(0)
        os.close(write_end)
        with os.fdopen(read_end) as pipe:
            report = json.loads(pipe.read() or '{}')
        os.waitpid(pid, 0)
        self.assertEqual(
            report,
            {'inherited': False, 'started': True, 'after_fetch': True, 'own_client': True},
        )
        # The parent's client is untouched and still polling.
        self.assertIs(flag_client.get_client(), parent_client)
        self.assertTrue(is_enabled(FLAG))

    def test_authenticates_and_identifies_itself(self):
        self.assertFalse(is_enabled(FLAG))
        self.assertTrue(flag_client.wait_until_started(timeout=10))
        register = next(r for r in self.unleash.requests if r[1] == '/api/client/register')
        fetch = next(r for r in self.unleash.requests if r[1].startswith('/api/client/features'))
        for request in (register, fetch):
            headers = {key.lower(): value for key, value in request[2].items()}
            self.assertEqual(headers['authorization'], '*:development.test-token')
            self.assertEqual(headers['unleash-appname'], 'eventhub-tests')
        self.assertEqual(register[3]['appName'], 'eventhub-tests')
        self.assertTrue(register[3]['instanceId'].endswith(f':{os.getpid()}'))


@override_settings(**UNLEASH_DOWN)
class ClientLifecycleTests(ClientResetMixin, TestCase):
    """The wrapper around a mocked UnleashClient."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(flag_client, 'UnleashClient')
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.sdk = self.factory.return_value

    def test_configured_from_settings_and_started_in_the_background(self):
        is_enabled(FLAG)
        self.assertTrue(flag_client.wait_until_started(timeout=5))
        kwargs = self.factory.call_args.kwargs
        self.assertEqual(kwargs['url'], 'http://127.0.0.1:9/api')
        self.assertEqual(kwargs['app_name'], 'eventhub-tests')
        self.assertEqual(kwargs['environment'], 'development')
        self.assertEqual(kwargs['custom_headers'], {'Authorization': '*:development.test-token'})
        self.assertEqual(kwargs['request_timeout'], 1)
        self.assertIsInstance(kwargs['cache'], flag_client.MemoryCache)
        self.sdk.initialize_client.assert_called_once_with()

    def test_lookups_never_wait_for_unleash(self):
        # Unleash accepts the connection but never answers.
        unblock = threading.Event()
        self.addCleanup(unblock.set)
        self.sdk.initialize_client.side_effect = lambda: unblock.wait(30)
        # The engine doesn't know any flag yet: the SDK asks the fallback.
        self.sdk.is_enabled.side_effect = lambda name, context, fallback_function: fallback_function(name, context)

        started = time.monotonic()
        self.assertFalse(is_enabled(FLAG))
        self.assertTrue(is_enabled(ON_BY_DEFAULT))
        self.assertLess(time.monotonic() - started, 5)
        self.assertFalse(flag_client.wait_until_started(timeout=0.1))  # still "connecting"
        unblock.set()
        self.assertTrue(flag_client.wait_until_started(timeout=5))

    def test_one_client_per_process(self):
        is_enabled(FLAG)
        is_enabled(FLAG)
        client_flags()
        self.assertEqual(self.factory.call_count, 1)

    def test_a_forked_process_gets_its_own_client(self):
        is_enabled(FLAG)
        flag_client.wait_until_started(timeout=5)
        parent_client = flag_client.get_client()
        with mock.patch.object(flag_client.os, 'getpid', return_value=flag_client._client_pid + 1):
            is_enabled(FLAG)
            flag_client.wait_until_started(timeout=5)
            self.assertEqual(self.factory.call_count, 2)
            # The parent's scheduler is not touched from the child.
            parent_client.destroy.assert_not_called()
            flag_client.reset_client()

    def test_fork_hook_drops_the_inherited_client(self):
        is_enabled(FLAG)
        flag_client.wait_until_started(timeout=5)
        inherited_lock = flag_client._lock
        flag_client._after_fork_in_child()
        self.assertIsNone(flag_client._client)
        self.assertIsNot(flag_client._lock, inherited_lock)
        is_enabled(FLAG)
        self.assertEqual(self.factory.call_count, 2)
        self.sdk.destroy.assert_not_called()

    def test_answer_comes_from_unleash_with_the_user_context(self):
        self.sdk.is_enabled.return_value = True
        user = make_user('dana', RoleChoices.ORGANIZER, is_staff=True)
        self.assertTrue(is_enabled(FLAG, user))
        name, context = self.sdk.is_enabled.call_args.args
        self.assertEqual(name, 'payments.freedompay')
        self.assertEqual(context, {'userId': str(user.pk), 'properties': {'role': 'organizer', 'isStaff': 'true'}})

    def test_fallback_is_the_registry_default(self):
        is_enabled(ON_BY_DEFAULT)
        fallback = self.sdk.is_enabled.call_args.kwargs['fallback_function']
        self.assertIs(fallback(ON_BY_DEFAULT.key, {}), True)
        is_enabled(FLAG)
        fallback = self.sdk.is_enabled.call_args.kwargs['fallback_function']
        self.assertIs(fallback(FLAG.key, {}), False)

    def test_sdk_errors_never_propagate(self):
        self.sdk.is_enabled.side_effect = RuntimeError('engine exploded')
        with self.assertLogs('featureflags.service', 'ERROR'):
            self.assertFalse(is_enabled(FLAG))
            self.assertTrue(is_enabled(ON_BY_DEFAULT))

    def test_reset_stops_the_client(self):
        is_enabled(FLAG)
        flag_client.reset_client()
        self.sdk.destroy.assert_called_once_with()
        self.assertIsNone(flag_client._client)


class ContextTests(TestCase):
    def test_anonymous_and_missing_users_have_no_context(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(build_context(None), {})
        self.assertEqual(build_context(AnonymousUser()), {})

    def test_no_personal_data_in_the_context(self):
        user = make_user('erik', email='erik@example.com', first_name='Erik')
        context = build_context(user)
        self.assertEqual(context, {'userId': str(user.pk), 'properties': {'role': 'attendee', 'isStaff': 'false'}})
        self.assertNotIn('erik', json.dumps(context).lower())


class OverrideTests(SimpleTestCase):
    def test_context_manager_and_nesting(self):
        with override_flags({FLAG: True}):
            self.assertTrue(is_enabled(FLAG))
            with override_flags({'payments.freedompay': False}):
                self.assertFalse(is_enabled(FLAG))
            self.assertTrue(is_enabled(FLAG))
        self.assertFalse(is_enabled(FLAG))

    @override_flags({Flags.CHECKIN_OFFLINE_SCANNER: True})
    def test_decorator(self):
        self.assertTrue(is_enabled(Flags.CHECKIN_OFFLINE_SCANNER))

    def test_unknown_flags_are_rejected(self):
        with self.assertRaises(KeyError):
            override_flags({'no.such_flag': True})


class FlaggedView(APIView):
    permission_classes = [IsAuthenticated, require_flag(Flags.CHECKIN_OFFLINE_SCANNER)]

    def get(self, request):
        return Response({'ok': True})


class RequireFlagTests(TestCase):
    def setUp(self):
        self.user = make_user('scanner')
        self.view = FlaggedView.as_view()

    def get(self, user=None):
        request = RequestFactory().get('/flagged/')
        if user:
            force_authenticate(request, user=user)
        return self.view(request)

    def test_hidden_while_off(self):
        self.assertEqual(self.get(self.user).status_code, 404)

    def test_available_when_on(self):
        with override_flags({Flags.CHECKIN_OFFLINE_SCANNER: True}):
            self.assertEqual(self.get(self.user).status_code, 200)

    def test_authentication_is_checked_first(self):
        with override_flags({Flags.CHECKIN_OFFLINE_SCANNER: True}):
            self.assertEqual(self.get().status_code, 401)
        self.assertEqual(self.get().status_code, 401)


class FeatureFlagsEndpointTests(TestCase):
    URL = '/api/v1/feature-flags/'

    def setUp(self):
        self.api = APIClient()
        self.user = make_user('frida')

    def test_requires_authentication(self):
        self.assertEqual(self.api.get(self.URL).status_code, 401)

    def test_returns_client_visible_flags_with_defaults(self):
        self.api.force_authenticate(self.user)
        response = self.api.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'flags': {flag.key: flag.default for flag in CLIENT_FLAGS}})
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('private', response['Cache-Control'])

    def test_evaluated_for_the_requesting_user(self):
        other = make_user('gustav')
        with mock.patch(
            'featureflags.service.get_client',
            return_value=mock.Mock(
                is_enabled=lambda name, context, fallback_function: context.get('userId') == str(other.pk)
            ),
        ):
            self.api.force_authenticate(self.user)
            mine = self.api.get(self.URL).json()['flags']
            self.api.force_authenticate(other)
            theirs = self.api.get(self.URL).json()['flags']
        self.assertFalse(any(mine.values()))
        self.assertTrue(all(theirs.values()))

    def test_server_only_flags_are_not_exposed(self):
        self.api.force_authenticate(self.user)
        keys = set(self.api.get(self.URL).json()['flags'])
        self.assertEqual(keys, {flag.key for flag in ALL_FLAGS if flag.client_visible})

    def test_no_unleash_secrets_in_the_response(self):
        self.api.force_authenticate(self.user)
        with override_settings(**UNLEASH_DOWN), mock.patch('featureflags.service.get_client', return_value=None):
            body = self.api.get(self.URL).content.decode()
        self.assertNotIn('test-token', body)
        self.assertNotIn('127.0.0.1:9', body)

    def test_schema_lists_every_client_flag(self):
        schema = yaml.safe_load((Path(settings.BASE_DIR) / 'openapi.yaml').read_text())
        component = schema['components']['schemas']['FeatureFlags']
        keys = {flag.key for flag in CLIENT_FLAGS}
        self.assertEqual(set(component['properties']), keys)
        self.assertEqual(set(component['required']), keys)
        operation = schema['paths']['/api/v1/feature-flags/']['get']
        self.assertEqual(set(operation['responses']), {'200', '401'})


class RateLimitFilterTests(SimpleTestCase):
    def record(self, msg='Unleash Client feature fetch failed due to exception: %s'):
        return logging.LogRecord('UnleashClient', logging.ERROR, __file__, 1, msg, ('down',), None)

    def test_repeats_are_dropped_within_the_interval_and_counted(self):
        log_filter = RateLimitFilter(interval=60)
        self.assertTrue(log_filter.filter(self.record()))
        self.assertFalse(log_filter.filter(self.record()))
        self.assertFalse(log_filter.filter(self.record()))
        self.assertTrue(log_filter.filter(self.record('another message')))
        with mock.patch('featureflags.log_filters.time.monotonic', return_value=time.monotonic() + 61):
            record = self.record()
            self.assertTrue(log_filter.filter(record))
        self.assertIn('[2 similar messages suppressed]', record.getMessage())
