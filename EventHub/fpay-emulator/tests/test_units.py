"""Unit tests: configuration, parsing helpers, money, cards, logging, entry point."""

from __future__ import annotations

import io
import json
import logging
from decimal import Decimal

import httpx
import pytest

from fpay_emulator import __main__ as entry
from fpay_emulator import cards, xmlio
from fpay_emulator.app import create_app
from fpay_emulator.callbacks import judge_reply
from fpay_emulator.config import ConfigError, Settings
from fpay_emulator.logs import JsonFormatter, configure, request_id_var, scrub
from fpay_emulator.money import negative, parse_amount, parse_optional_amount, percent_of, plain, two_places
from fpay_emulator.params import php_nest, php_scalar
from fpay_emulator.signature import Pairs

from .conftest import base_env

# -- configuration ------------------------------------------------------------


def test_merchants_and_per_merchant_settings(tmp_path) -> None:
    env = base_env(
        tmp_path,
        FPAY_MERCHANTS=' 1:a , 2:b:with:colons ,',
        FPAY_MERCHANT_1_NAME='Concert hall',
        FPAY_MERCHANT_1_CHECK_URL='https://shop.example/check',
        FPAY_MERCHANT_1_REQUEST_METHOD='xml',
    )
    settings = Settings.from_env(env)
    assert settings.merchant('1').display_name == 'Concert hall'
    assert settings.merchant('1').request_method == 'XML'
    assert settings.merchant('2').secret == 'b:with:colons'
    assert settings.merchant('2').display_name == 'Merchant 2'
    assert settings.merchant(None) is None
    assert 'secret' not in repr(settings.merchant('1'))
    assert settings.tz.key == 'Asia/Almaty'


@pytest.mark.parametrize(
    'overrides',
    [
        {'FPAY_MERCHANTS': ''},
        {'FPAY_MERCHANTS': ','},
        {'FPAY_MERCHANTS': 'abc:secret'},
        {'FPAY_MERCHANTS': '123'},
        {'FPAY_MERCHANTS': '1:a', 'FPAY_MERCHANT_1_REQUEST_METHOD': 'PUT'},
        {'FPAY_MERCHANTS': '1:a', 'FPAY_MERCHANT_1_RESULT_URL': 'ftp://x'},
        {'FPAY_TIMEZONE': 'Mars/Olympus'},
        {'FPAY_COMMISSION_PERCENT': 'many'},
        {'FPAY_COMMISSION_PERCENT': '100'},
        {'FPAY_DEFAULT_CURRENCY': 'JPY'},
        {'FPAY_EXPIRY_PG_RESULT': '1'},
        {'FPAY_PUBLIC_URL': 'fpay.local'},
        {'FPAY_REPLY_MODE': 'chill'},
        {'FPAY_CHECK_ENABLED': 'maybe'},
        {'FPAY_RETRY_INTERVAL_SECONDS': '0'},
        {'FPAY_RETRY_INTERVAL_SECONDS': 'soon'},
        {'FPAY_CALLBACK_TIMEOUT_SECONDS': 'x'},
        {'FPAY_CALLBACK_TIMEOUT_SECONDS': '0'},
    ],
)
def test_configuration_errors(tmp_path, overrides: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(base_env(tmp_path, **overrides))


def test_boolean_spellings(tmp_path) -> None:
    assert Settings.from_env(base_env(tmp_path, FPAY_CHECK_ENABLED='yes')).check_enabled
    assert not Settings.from_env(base_env(tmp_path, FPAY_CONTROL_ENABLED='off')).control_enabled


# -- parsing helpers -----------------------------------------------------------


def test_php_nest() -> None:
    tree = php_nest(
        [
            ('a', '1'),
            ('list[]', 'x'),
            ('list[]', 'y'),
            ('deep[k][]', 'z'),
            ('a', '2'),
            ('scalar', 's'),
            ('scalar[k]', 'replaced'),
            ('broken[', 'kept'),
            ('list[5]', 'five'),
            ('list[]', 'six'),
        ]
    )
    assert tree == {
        'a': '2',
        'list': {'0': 'x', '1': 'y', '5': 'five', '6': 'six'},
        'deep': {'k': {'0': 'z'}},
        'scalar': {'k': 'replaced'},
        'broken[': 'kept',
    }
    assert list(tree) == ['a', 'list', 'deep', 'scalar', 'broken[']


@pytest.mark.parametrize(
    ('value', 'expected'),
    [(None, ''), (True, '1'), (False, ''), (100, '100'), (Decimal('100.50'), '100.5'), (Decimal('100.0'), '100'),
     (1.25, '1.25'), ('x', 'x')],
)  # fmt: skip
def test_php_scalar(value: object, expected: str) -> None:
    assert php_scalar(value) == expected


def test_xml_roundtrip_and_escaping() -> None:
    fields = [('pg_a', 'x & <y>'), ('pg_list', Pairs([('pg_item', '1'), ('pg_item', '2')])), ('pg_empty', None)]
    document = xmlio.render('response', fields)
    parsed = xmlio.parse(document, root='response')
    assert parsed[0] == ('pg_a', 'x & <y>')
    assert list(parsed[1][1]) == [('pg_item', '1'), ('pg_item', '2')]
    assert xmlio.first(parsed, 'pg_empty') == ''
    assert xmlio.first(parsed, 'missing', 'd') == 'd'
    with pytest.raises(xmlio.XmlError):
        xmlio.parse(document, root='request')
    with pytest.raises(xmlio.XmlError):
        xmlio.parse('<!DOCTYPE x [<!ENTITY a "b">]><request>&a;</request>')
    assert xmlio.render('response', {'pg_status': 'error'}, pretty=False).endswith(
        b'<response><pg_status>error</pg_status></response>'
    )


# -- money and cards -------------------------------------------------------------


def test_money() -> None:
    assert parse_amount('100.5') == Decimal('100.5')
    assert parse_amount('0.001') is None
    assert parse_amount(5) is None  # type: ignore[arg-type]
    assert parse_optional_amount('0') == Decimal(0)
    assert parse_optional_amount('1.239', truncate=True) == Decimal('1.23')
    assert parse_optional_amount('999999999') is None
    assert parse_optional_amount(None) is None  # type: ignore[arg-type]
    assert (plain(Decimal('100.00')), plain(Decimal('482.50')), plain(Decimal('0'))) == ('100', '482.5', '0')
    assert two_places(Decimal('1')) == '1.00'
    assert (negative(Decimal('20')), negative(Decimal('0'))) == ('-20.00', '0.00')
    assert percent_of(Decimal('1500'), Decimal('2.5')) == Decimal('37.50')


def test_cards() -> None:
    assert cards.mask('5483185555550293') == '5483-18XX-XXXX-0293'
    assert cards.mask('6224466455690681278') == '6224-46XX-XXXX-XXX1-278'
    assert [cards.brand(p) for p in ('4111', '5111', '2221', '6224', '9999')] == ['VI', 'MC', 'MC', 'UP', 'XX']
    assert cards.luhn_ok('4111111111111111')
    assert not cards.valid_pan('4111111111111112')
    assert cards.valid_pan('62528733472390953')
    assert cards.normalise_pan('4111 1111-1111 1111') == '4111111111111111'
    assert cards.scenario_for_card('4916307416334310', True) == (cards.THREE_DS_SUCCESS, None)
    record = cards.card_record('4111111111111111', '12', '30', 'A B')
    assert '4111111111111111' not in json.dumps(record)


# -- logging ------------------------------------------------------------------------


def test_json_formatter_scrubs_and_carries_context() -> None:
    formatter = JsonFormatter()
    token = request_id_var.set('req-1')
    try:
        record = logging.LogRecord('fpay.test', logging.INFO, __file__, 1, 'card %s', ('4111111111111111',), None)
        record.payment_id = 42
        record.fields = {'pan': '5548398681700148'}
        entry = json.loads(formatter.format(record))
    finally:
        request_id_var.reset(token)
    assert entry['msg'] == 'card 411111…1111'
    assert entry['request_id'] == 'req-1'
    assert entry['payment_id'] == 42
    assert entry['fields'] == {'pan': '554839…0148'}
    assert scrub(['1234567890123', 5]) == ['123456…0123', 5]
    try:
        raise ValueError('boom')
    except ValueError:
        import sys

        record = logging.LogRecord('x', logging.ERROR, __file__, 1, 'failed', (), sys.exc_info())
    assert 'ValueError' in json.loads(formatter.format(record))['exc']


def test_configure_installs_json_handler() -> None:
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        configure('DEBUG')
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert logging.getLogger('uvicorn.access').disabled
    finally:
        root.handlers[:], level = saved
        root.setLevel(level)
        logging.getLogger('uvicorn.access').disabled = False


async def test_request_id_is_kept_or_generated(tmp_path, caplog) -> None:
    app = create_app(Settings.from_env(base_env(tmp_path)), run_scheduler=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fpay.test') as client:
        with caplog.at_level(logging.INFO, logger='fpay.access'):
            kept = await client.get('/status/healthcheck', headers={'X-Request-Id': 'abc-123'})
            replaced = await client.get('/status/healthcheck', headers={'X-Request-Id': 'bad id!'})
    await app.emulator.stop()
    assert kept.headers['x-request-id'] == 'abc-123'
    assert replaced.headers['x-request-id'] != 'bad id!'
    assert len(replaced.headers['x-request-id']) == 32
    access = [r for r in caplog.records if r.name == 'fpay.access']
    assert access[0].status == 200
    assert access[0].path == '/status/healthcheck'


async def test_lifespan_starts_and_stops_the_scheduler(tmp_path) -> None:
    app = create_app(Settings.from_env(base_env(tmp_path, FPAY_SCHEDULER_TICK_SECONDS='0.05')))
    messages = iter([{'type': 'lifespan.startup'}, {'type': 'lifespan.shutdown'}])
    sent: list[str] = []

    async def receive() -> dict:
        return next(messages)

    async def send(message: dict) -> None:
        sent.append(message['type'])

    await app({'type': 'lifespan', 'asgi': {'version': '3.0'}, 'state': {}}, receive, send)
    assert sent == ['lifespan.startup.complete', 'lifespan.shutdown.complete']


# -- entry point --------------------------------------------------------------------


def test_main_reports_configuration_errors(monkeypatch) -> None:
    monkeypatch.delenv('FPAY_MERCHANTS', raising=False)
    stderr = io.StringIO()
    monkeypatch.setattr('sys.stderr', stderr)
    assert entry.main() == 2
    assert 'FPAY_MERCHANTS is required' in stderr.getvalue()


def test_main_runs_uvicorn(monkeypatch, tmp_path) -> None:
    for key, value in base_env(tmp_path).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('FPAY_PORT', '18999')
    calls: dict = {}
    monkeypatch.setattr(entry.uvicorn, 'run', lambda app, **kwargs: calls.update(kwargs, app=app))
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        assert entry.main() == 0
    finally:
        root.handlers[:], level = saved
        root.setLevel(level)
        logging.getLogger('uvicorn.access').disabled = False
    assert calls['port'] == 18999
    assert calls['workers'] == 1
    calls['app'].emulator.store.close()


# -- strict reply judgement -------------------------------------------------------------


@pytest.mark.parametrize(
    ('body', 'problem'),
    [
        (b'<response><pg_status>fine</pg_status><pg_description/><pg_salt>s</pg_salt></response>', 'pg_status'),
        (b'<response><pg_status>ok</pg_status><pg_description/></response>', 'pg_salt is missing'),
        (b'<response><pg_status>ok</pg_status><pg_description/><pg_salt>s</pg_salt></response>', 'pg_sig is missing'),
        (b'<request><pg_status>ok</pg_status></request>', 'not a <response>'),
    ],
)
def test_strict_reply_problems(tmp_path, body: bytes, problem: str) -> None:
    settings = Settings.from_env(base_env(tmp_path))
    verdict = judge_reply(settings, status_code=200, body=body, script='result', secret='k', sent_salt='s')
    assert verdict.verdict == 'invalid'
    assert problem in verdict.detail


def test_lenient_reply_with_unknown_status(tmp_path) -> None:
    settings = Settings.from_env(base_env(tmp_path, FPAY_REPLY_MODE='lenient'))
    body = b'<response><pg_status>whatever</pg_status></response>'
    assert judge_reply(settings, status_code=200, body=body, script='r', secret='k', sent_salt='s').verdict == 'ok'
    assert judge_reply(settings, status_code=503, body=b'', script='r', secret='k', sent_salt='s').verdict == (
        'http_error'
    )
