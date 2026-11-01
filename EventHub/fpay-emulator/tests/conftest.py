from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from fpay_emulator import xmlio
from fpay_emulator.app import EmulatorApp, create_app
from fpay_emulator.config import Settings
from fpay_emulator.signature import Pairs, make_signature, script_name, verify_signature

from .merchant import FakeMerchant

MERCHANT_ID = '12345'
SECRET = 'test_secret_key'
OTHER_ID = '777'
OTHER_SECRET = 'other_secret'
BASE_URL = 'http://fpay.test'


@dataclass
class Emu:
    app: EmulatorApp
    client: httpx.AsyncClient
    merchant: FakeMerchant
    settings: Settings

    @property
    def gw(self):
        return self.app.emulator.gateway

    async def call(
        self,
        path: str,
        params: dict[str, Any],
        *,
        secret: str = SECRET,
        script: str | None = None,
        sign: bool = True,
        method: str = 'POST',
    ) -> Pairs:
        response = await self.raw(path, params, secret=secret, script=script, sign=sign, method=method)
        assert response.status_code == 200, response.text
        return xmlio.parse(response.content, root='response')

    async def raw(
        self,
        path: str,
        params: dict[str, Any],
        *,
        secret: str = SECRET,
        script: str | None = None,
        sign: bool = True,
        method: str = 'POST',
    ) -> httpx.Response:
        params = dict(params)
        params.setdefault('pg_merchant_id', MERCHANT_ID)
        params.setdefault('pg_salt', 'a1b2c3d4')
        if sign:
            params['pg_sig'] = make_signature(script or script_name(path), params, secret)
        if method == 'GET':
            return await self.client.get(path, params=params)
        return await self.client.post(path, data=params)

    async def init(self, **params: Any) -> Pairs:
        data = {'pg_amount': '1500', 'pg_description': 'Ticket A', 'pg_order_id': 'ORD-1'}
        data.update({k: v for k, v in params.items() if v is not None})
        reply = await self.call('/init_payment', data)
        assert xmlio.first(reply, 'pg_status') == 'ok', reply
        return reply

    async def status(self, payment_id: str, **extra: Any) -> Pairs:
        return await self.call('/get_status3.php', {'pg_payment_id': payment_id, **extra})

    async def control(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return await self.client.request(method, f'/_emulator{path}', **kwargs)

    async def complete(self, payment_id: str, **body: Any) -> dict[str, Any]:
        response = await self.control('POST', f'/payments/{payment_id}/complete', json=body)
        assert response.status_code == 200, response.text
        return response.json()

    async def state(self, payment_id: str) -> dict[str, Any]:
        response = await self.control('GET', f'/payments/{payment_id}')
        assert response.status_code == 200, response.text
        return response.json()

    async def advance(self, seconds: float) -> dict[str, Any]:
        response = await self.control('POST', '/clock', json={'advance_seconds': seconds})
        assert response.status_code == 200, response.text
        return response.json()


def field(reply: Pairs, name: str) -> Any:
    return xmlio.first(reply, name)


def assert_signed(reply: Pairs, script: str, secret: str = SECRET) -> None:
    assert verify_signature(script, reply, secret, field(reply, 'pg_sig')), reply


def base_env(tmp_path: Any, **overrides: str) -> dict[str, str]:
    env = {
        'FPAY_MERCHANTS': f'{MERCHANT_ID}:{SECRET},{OTHER_ID}:{OTHER_SECRET}',
        'FPAY_DB_PATH': str(tmp_path / 'fpay.sqlite3'),
        'FPAY_PUBLIC_URL': BASE_URL,
        'FPAY_RETRY_INTERVAL_SECONDS': '1',
        'FPAY_RETRY_WINDOW_SECONDS': '4',
        'FPAY_CALLBACK_TIMEOUT_SECONDS': '2',
        'FPAY_CHECK_TIMEOUT_SECONDS': '2',
    }
    env.update(overrides)
    return env


EmuFactory = Callable[..., Awaitable[Emu]]


@pytest.fixture
def merchant() -> Iterator[FakeMerchant]:
    server = FakeMerchant(secret=SECRET)
    server.start()
    yield server
    server.stop()


@pytest.fixture
async def make_emu(tmp_path: Any, merchant: FakeMerchant) -> AsyncIterator[EmuFactory]:
    created: list[Emu] = []

    async def factory(**env: str) -> Emu:
        settings = Settings.from_env(base_env(tmp_path, **env))
        app = create_app(settings, run_scheduler=False)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)
        emu = Emu(app=app, client=client, merchant=merchant, settings=settings)
        created.append(emu)
        return emu

    yield factory
    for emu in created:
        await emu.client.aclose()
        await emu.app.emulator.stop()


@pytest.fixture
async def emu(make_emu: EmuFactory) -> Emu:
    return await make_emu()
