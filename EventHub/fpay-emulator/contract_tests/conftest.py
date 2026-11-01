"""Configuration of the HTTP-only contract suite (see README, "Contract suite").

Environment:

* ``FPAY_CONTRACT_BASE_URL``: gateway base URL, e.g. ``http://localhost:18080`` or
  ``https://api.freedompay.kz``. Without it the whole suite is skipped.
* ``FPAY_CONTRACT_MERCHANT_ID`` / ``FPAY_CONTRACT_SECRET``: merchant credentials.
* ``FPAY_CONTRACT_CONTROL_TOKEN``: the emulator's ``X-Emulator-Token`` (optional).
* ``FPAY_CONTRACT_ALLOW_DESTRUCTIVE=1``: allow paying and refunding on a target
  that has no ``/_emulator`` control API (the real gateway). The payment is then
  made by hand in a browser: run pytest with ``-s`` to see the link.
* ``FPAY_CONTRACT_MANUAL_TIMEOUT``: seconds to wait for that manual payment (300).
* ``FPAY_CONTRACT_AMOUNT`` / ``FPAY_CONTRACT_CURRENCY``: test amount (10 KZT).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import pytest

from .fpay_client import Gateway


@dataclass
class Target:
    gateway: Gateway
    control_url: str | None
    control_headers: dict[str, str]
    allow_destructive: bool
    manual_timeout: float
    amount: str
    currency: str

    @property
    def is_emulator(self) -> bool:
        return self.control_url is not None

    def control(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        assert self.control_url is not None
        return httpx.request(method, f'{self.control_url}{path}', headers=self.control_headers, timeout=30, **kwargs)


def _detect_control(base_url: str, headers: dict[str, str]) -> str | None:
    try:
        response = httpx.get(f'{base_url}/_emulator/clock', headers=headers, timeout=10)
    except httpx.HTTPError:
        return None
    if response.status_code == 200 and response.headers.get('content-type', '').startswith('application/json'):
        return f'{base_url}/_emulator'
    if response.status_code == 401:
        pytest.exit('the target is an emulator but FPAY_CONTRACT_CONTROL_TOKEN is missing or wrong', returncode=2)
    return None


@pytest.fixture(scope='session')
def target() -> Target:
    base_url = os.environ.get('FPAY_CONTRACT_BASE_URL', '').rstrip('/')
    if not base_url:
        pytest.skip('FPAY_CONTRACT_BASE_URL is not set')
    merchant_id = os.environ.get('FPAY_CONTRACT_MERCHANT_ID', '')
    secret = os.environ.get('FPAY_CONTRACT_SECRET', '')
    if not merchant_id or not secret:
        pytest.skip('FPAY_CONTRACT_MERCHANT_ID and FPAY_CONTRACT_SECRET are required')
    token = os.environ.get('FPAY_CONTRACT_CONTROL_TOKEN', '')
    headers = {'X-Emulator-Token': token} if token else {}
    return Target(
        gateway=Gateway(base_url, merchant_id, secret),
        control_url=_detect_control(base_url, headers),
        control_headers=headers,
        allow_destructive=os.environ.get('FPAY_CONTRACT_ALLOW_DESTRUCTIVE') == '1',
        manual_timeout=float(os.environ.get('FPAY_CONTRACT_MANUAL_TIMEOUT', '300')),
        amount=os.environ.get('FPAY_CONTRACT_AMOUNT', '10'),
        currency=os.environ.get('FPAY_CONTRACT_CURRENCY', 'KZT'),
    )
