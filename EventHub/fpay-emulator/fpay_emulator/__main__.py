"""``python -m fpay_emulator``: run the emulator with uvicorn (one process)."""

from __future__ import annotations

import os
import sys

import uvicorn

from .app import create_app
from .config import ConfigError, Settings
from .logs import configure


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f'fpay-emulator: configuration error: {exc}', file=sys.stderr)
        return 2
    configure(settings.log_level)
    app = create_app(settings)
    uvicorn.run(
        app,
        host=os.environ.get('FPAY_HOST', '0.0.0.0'),  # noqa: S104 - a container service
        port=int(os.environ.get('FPAY_PORT', '8080')),
        log_config=None,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get('FPAY_FORWARDED_ALLOW_IPS', '127.0.0.1'),
        workers=1,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
