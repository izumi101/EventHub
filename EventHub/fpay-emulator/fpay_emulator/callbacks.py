"""Check and Result callbacks to the merchant (spec section 4).

* Check (S5): synchronous, before authorisation. Anything but a valid ``ok``
  (``rejected``, ``error``, an invalid reply, a non-200, no answer in time)
  refuses the payment.
* Result (S4): after the payment settles. A non-200 or (strict mode) invalid
  reply is retried every ``FPAY_RETRY_INTERVAL_SECONDS`` for
  ``FPAY_RETRY_WINDOW_SECONDS`` counted from the first attempt. Only the first
  attempt carries ``pg_can_reject=1``; retries carry the same business data.
  The schedule lives in SQLite, so it survives a restart.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx

from . import xmlio
from .clock import Clock
from .config import Merchant, Settings
from .models import SUCCESS, Payment, from_iso, iso
from .money import percent_of, plain
from .protocol import signed_for_url, with_query
from .signature import Pairs, script_name, verify_signature
from .store import Store

log = logging.getLogger('fpay.callbacks')

OK = 'ok'
REJECTED = 'rejected'
ERROR = 'error'
INVALID = 'invalid'
HTTP_ERROR = 'http_error'
TIMEOUT = 'timeout'
CONNECTION_ERROR = 'connection_error'
REPLY_STATUSES = (OK, REJECTED, ERROR)
_MAX_LOGGED_BODY = 4000


@dataclass
class Verdict:
    verdict: str
    description: str | None = None
    detail: str | None = None
    http_status: int | None = None


def judge_reply(
    settings: Settings,
    *,
    status_code: int,
    body: bytes,
    script: str,
    secret: str,
    sent_salt: str,
) -> Verdict:
    """Classify a merchant's answer to a Check or Result call."""
    if status_code != 200:
        return Verdict(HTTP_ERROR, detail=f'HTTP {status_code}', http_status=status_code)
    try:
        pairs = xmlio.parse(body, root='response')
    except xmlio.XmlError as exc:
        if settings.reply_mode == 'lenient':
            return Verdict(OK, detail='lenient: non-XML 200 accepted', http_status=200)
        return Verdict(INVALID, detail=f'reply is not a <response> XML document ({exc})', http_status=200)
    status = xmlio.first(pairs, 'pg_status')
    description = xmlio.first(pairs, 'pg_description')
    if settings.reply_mode == 'lenient':
        if status in REPLY_STATUSES:
            return Verdict(status, description=description, detail='lenient: signature not checked', http_status=200)
        return Verdict(OK, detail='lenient: 200 accepted', http_status=200)
    problems = []
    if status not in REPLY_STATUSES:
        problems.append('pg_status must be ok, rejected or error')
    if description is None:
        problems.append('pg_description is missing')
    salt = xmlio.first(pairs, 'pg_salt')
    if not salt:
        problems.append('pg_salt is missing')
    elif settings.reply_salt_must_echo and salt != sent_salt:
        problems.append('pg_salt does not echo the request salt')
    sig = xmlio.first(pairs, 'pg_sig')
    if sig is None:
        problems.append('pg_sig is missing')
    elif not verify_signature(script, pairs, secret, sig):
        problems.append(f'pg_sig is invalid for script name {script!r}')
    if problems:
        return Verdict(INVALID, description=description, detail='; '.join(problems), http_status=200)
    return Verdict(status, description=description, http_status=200)


def commission(settings: Settings, payment: Payment) -> dict[str, str]:
    fee = percent_of(payment.amount, settings.commission_percent)
    if settings.commission_payer == 'client':
        return {
            'net': plain(payment.amount),
            'ps_amount': plain(payment.amount),
            'ps_full': plain(payment.amount + fee),
        }
    return {'net': plain(payment.amount - fee), 'ps_amount': plain(payment.amount), 'ps_full': plain(payment.amount)}


def payment_date(settings: Settings, payment: Payment) -> str:
    moment = payment.paid_at or payment.created_at
    return moment.astimezone(settings.tz).strftime('%Y-%m-%d %H:%M:%S')


def check_fields(settings: Settings, payment: Payment) -> list[tuple[str, str]]:
    money = commission(settings, payment)
    fields: list[tuple[str, str]] = []
    if payment.order_id is not None:
        fields.append(('pg_order_id', payment.order_id))
    fields += [
        ('pg_payment_id', str(payment.payment_id)),
        ('pg_amount', plain(payment.amount)),
        ('pg_currency', payment.currency),
        ('pg_ps_amount', money['ps_amount']),
        ('pg_ps_currency', payment.currency),
        ('pg_ps_full_amount', money['ps_full']),
    ]
    fields += [(k, v) for k, v in payment.custom_params]
    return fields


def result_fields(settings: Settings, payment: Payment, pg_result: str) -> list[tuple[str, str]]:
    """Business data of a Result call, without ``pg_can_reject``/``pg_salt``/``pg_sig``."""
    success = pg_result == '1'
    money = commission(settings, payment)
    fields: list[tuple[str, str]] = []
    if payment.order_id is not None:
        fields.append(('pg_order_id', payment.order_id))
    fields += [
        ('pg_payment_id', str(payment.payment_id)),
        ('pg_amount', plain(payment.amount)),
        ('pg_currency', payment.currency),
        ('pg_net_amount', money['net'] if success else '0'),
    ]
    if success:
        # "may be missing on failure" (L2): never sent on failure here.
        fields += [
            ('pg_ps_amount', money['ps_amount']),
            ('pg_ps_full_amount', money['ps_full']),
            ('pg_ps_currency', payment.currency),
        ]
    fields += [
        ('pg_description', payment.description),
        ('pg_result', pg_result),
        ('pg_payment_date', payment_date(settings, payment)),
        ('pg_can_reject', '0'),
        ('pg_testing_mode', '1' if payment.testing_mode else '0'),
    ]
    if success and payment.card:
        fields.append(('pg_captured', '1' if payment.captured else '0'))
    if payment.user_phone:
        fields.append(('pg_user_phone', payment.user_phone))
    if payment.user_email:
        fields += [('pg_user_contact_email', payment.user_email), ('pg_need_email_notification', '1')]
    if payment.card:
        fields += [
            ('pg_payment_method', 'bankcard'),
            ('pg_card_pan', payment.card['pan']),
            ('pg_card_exp', payment.card['exp']),
            ('pg_card_owner', payment.card['owner']),
            ('pg_card_brand', payment.card['brand']),
        ]
    if payment.reference:
        fields.append(('pg_reference', payment.reference))
    if not success and settings.result_failure_fields and payment.failure_code:
        fields += [
            ('pg_failure_code', payment.failure_code),
            ('pg_failure_description', payment.failure_description or ''),
        ]
    fields += [(k, v) for k, v in payment.custom_params]
    return fields


def result_code(settings: Settings, payment: Payment) -> str:
    if payment.status == SUCCESS:
        return '1'
    if payment.failure_code == '10018' and payment.card is None:
        return settings.expiry_pg_result
    return '0'


class Notifier:
    """Sends Check/Result calls and owns the Result retry schedule."""

    def __init__(self, settings: Settings, store: Store, clock: Clock, http: httpx.AsyncClient) -> None:
        self.settings = settings
        self.store = store
        self.clock = clock
        self.http = http

    def _merchant(self, payment: Payment) -> Merchant:
        merchant = self.settings.merchant(payment.merchant_id)
        if merchant is None:  # configuration changed under a stored payment
            raise RuntimeError(f'merchant {payment.merchant_id} is no longer configured')
        return merchant

    async def _send(
        self, url: str, method: str, fields: list[tuple[str, str]], secret: str, *, timeout: float
    ) -> tuple[Verdict, dict[str, Any]]:
        include_query = self.settings.callback_sign_url_query == 'always' or (
            self.settings.callback_sign_url_query == 'get_only' and method == 'GET'
        )
        signed, _ = signed_for_url(url, secret, fields, include_url_query=include_query)
        salt = xmlio.first(signed, 'pg_salt')
        script = script_name(url)
        request_log: dict[str, Any] = {'url': url, 'method': method, 'script_name': script, 'fields': list(signed)}
        started = time.perf_counter()
        try:
            if method == 'GET':
                target = with_query(url, signed)
                request_log['url'] = target
                response = await self.http.get(target, timeout=timeout)
            elif method == 'XML':
                document = xmlio.render('request', signed).decode('utf-8')
                request_log['body'] = document
                response = await self.http.post(url, data={'pg_xml': document}, timeout=timeout)
            else:
                response = await self.http.post(url, data=dict(signed), timeout=timeout)
        except httpx.TimeoutException as exc:
            verdict = Verdict(TIMEOUT, detail=f'no answer within {timeout:g}s ({exc.__class__.__name__})')
            body = b''
        except httpx.HTTPError as exc:
            verdict = Verdict(CONNECTION_ERROR, detail=f'{exc.__class__.__name__}: {exc}'[:300])
            body = b''
        else:
            body = response.content
            verdict = judge_reply(
                self.settings,
                status_code=response.status_code,
                body=body,
                script=script,
                secret=secret,
                sent_salt=salt or '',
            )
        entry = {
            'request': request_log,
            'http_status': verdict.http_status,
            'reply': body[:_MAX_LOGGED_BODY].decode('utf-8', errors='replace'),
            'verdict': verdict.verdict,
            'reply_description': verdict.description,
            'detail': verdict.detail,
            'duration_ms': round((time.perf_counter() - started) * 1000, 1),
        }
        return verdict, entry

    # -- Check --------------------------------------------------------------

    async def check(self, payment: Payment) -> Verdict | None:
        """``None`` when no check applies; otherwise the merchant's verdict."""
        if not self.settings.check_enabled or not payment.check_url:
            return None
        merchant = self._merchant(payment)
        verdict, entry = await self._send(
            payment.check_url,
            payment.request_method,
            check_fields(self.settings, payment),
            merchant.secret,
            timeout=self.settings.check_timeout_seconds,
        )
        entry.update({'kind': 'check', 'attempt': 1, 'at': iso(self.clock.now()), 'can_reject': None})
        self.store.add_delivery(payment.payment_id, None, entry)
        log.info(
            'check callback',
            extra={'payment_id': payment.payment_id, 'verdict': verdict.verdict, 'detail': verdict.detail},
        )
        return verdict

    # -- Result -------------------------------------------------------------

    def enqueue_result(self, payment: Payment) -> int | None:
        if not payment.result_url:
            return None
        now = self.clock.now()
        data = {
            'url': payment.result_url,
            'method': payment.request_method,
            'fields': result_fields(self.settings, payment, result_code(self.settings, payment)),
            'can_reject_initial': bool(payment.can_reject and payment.status == SUCCESS),
        }
        return self.store.create_job(payment.payment_id, 'result', iso(now), iso(now), data)

    async def deliver_job(self, job_id: int, on_reject: Callable[[int, str | None], None]) -> dict[str, Any] | None:
        """Run one attempt of a pending job. ``None`` if the job is not pending."""
        job = self.store.claim_job(job_id)
        if job is None:
            return None
        payment = self.store.get_payment(job['payment_id'])
        now = self.clock.now()
        if payment is None:
            self.store.finish_job(
                job_id, state='failed', attempts=job['attempts'], first_attempt_iso=None, next_attempt_iso=iso(now)
            )
            return None
        data = job['data']
        attempt = job['attempts'] + 1
        can_reject = bool(data['can_reject_initial']) and attempt == 1
        fields = [(k, ('1' if can_reject else '0') if k == 'pg_can_reject' else v) for k, v in data['fields']]
        try:
            merchant = self._merchant(payment)
        except RuntimeError as exc:
            log.error('result callback impossible', extra={'payment_id': payment.payment_id, 'detail': str(exc)})
            self.store.finish_job(
                job_id, state='failed', attempts=attempt, first_attempt_iso=iso(now), next_attempt_iso=iso(now)
            )
            return None
        verdict, entry = await self._send(
            data['url'], data['method'], fields, merchant.secret, timeout=self.settings.callback_timeout_seconds
        )
        delivered = verdict.verdict in (OK, REJECTED) or (
            verdict.verdict == ERROR and not self.settings.retry_on_error_reply
        )
        first_iso = job['first_attempt_at'] or iso(now)
        outcome = 'delivered' if delivered else 'retry'
        if delivered:
            state, next_iso = 'delivered', iso(now)
        else:
            next_at = from_iso(first_iso) + timedelta(seconds=self.settings.retry_interval_seconds * attempt)
            if (next_at - from_iso(first_iso)).total_seconds() > self.settings.retry_window_seconds:
                state, next_iso, outcome = 'failed', iso(now), 'gave_up'
            else:
                state, next_iso = 'pending', iso(next_at)
        if verdict.verdict == REJECTED:
            outcome = 'rejected' if can_reject else 'rejected_ignored'
        entry.update(
            {'kind': 'result', 'attempt': attempt, 'at': iso(now), 'can_reject': can_reject, 'outcome': outcome}
        )
        self.store.add_delivery(payment.payment_id, job_id, entry)
        self.store.finish_job(
            job_id, state=state, attempts=attempt, first_attempt_iso=first_iso, next_attempt_iso=next_iso
        )
        if attempt == 1 and payment.can_reject:
            # After the first attempt (failed or not) the payment cannot be refused any more (S4).
            payment.can_reject = False
            self.store.save_payment(payment)
        if verdict.verdict == REJECTED and can_reject:
            on_reject(payment.payment_id, verdict.description)
        log.info(
            'result callback',
            extra={
                'payment_id': payment.payment_id,
                'attempt': attempt,
                'verdict': verdict.verdict,
                'outcome': outcome,
                'detail': verdict.detail,
            },
        )
        return entry

    async def replay_result(self, payment: Payment) -> dict[str, Any]:
        """Send the Result call once more with the original business data."""
        jobs = [j for j in self.store.jobs(payment.payment_id) if j['kind'] == 'result']
        if jobs:
            data = jobs[-1]['data']
            url, method, fields = data['url'], data['method'], data['fields']
        elif payment.result_url and payment.is_final:
            url, method = payment.result_url, payment.request_method
            fields = result_fields(self.settings, payment, result_code(self.settings, payment))
        else:
            raise LookupError('this payment has no Result callback to replay')
        merchant = self._merchant(payment)
        verdict, entry = await self._send(
            url, method, Pairs(fields), merchant.secret, timeout=self.settings.callback_timeout_seconds
        )
        outcome = 'replayed'
        if verdict.verdict == REJECTED:
            outcome = 'rejected_ignored'
        entry.update(
            {'kind': 'replay', 'attempt': None, 'at': iso(self.clock.now()), 'can_reject': False, 'outcome': outcome}
        )
        self.store.add_delivery(payment.payment_id, None, entry)
        return entry
