"""Who may run the demo seed commands (`seed_data`, `seed_showcase`).

Demo content is for development (`DJANGO_DEBUG=1`), where the demo accounts
use the documented password `password123`. A public demo deployment runs with
`DJANGO_DEBUG=0` and may load the same content only when the operator says so
explicitly (`--i-know-this-is-a-demo`), and then never with a publicly known
password: the demo accounts get `DJANGO_SEED_DEMO_PASSWORD` from the
server's `.env` (docs/DEPLOY.md, "Demo data").

`seed_demo_kz` stays DEBUG-only: hundreds of accounts on undeliverable
`*.eventhub.local` addresses would make the worker send reminder emails
through the deployment's real SMTP account.
"""

import os

from django.conf import settings
from django.core.management.base import CommandError

FLAG = '--i-know-this-is-a-demo'
PASSWORD_ENV = 'DJANGO_SEED_DEMO_PASSWORD'  # noqa: S105 - the variable's name, not a password
DEV_PASSWORD = 'password123'  # noqa: S105 - documented development password, DEBUG only
MIN_PASSWORD_LENGTH = 12


def add_demo_flag(parser) -> None:
    parser.add_argument(
        FLAG,
        action='store_true',
        dest='demo_deployment',
        help=(
            f'Allow demo content with DJANGO_DEBUG=0 (a public demo deployment). Demo accounts then get '
            f'the password from {PASSWORD_ENV} instead of the development password.'
        ),
    )


def check_allowed(command: str, options: dict) -> None:
    """Raise CommandError unless demo content may be created here."""
    if settings.DEBUG:
        return
    if not options.get('demo_deployment'):
        raise CommandError(
            f'{command} creates demo content; run it only with DJANGO_DEBUG=1, or on a public demo '
            f'deployment with {FLAG} and {PASSWORD_ENV} set (docs/DEPLOY.md).'
        )


def demo_password(command: str, options: dict) -> str:
    """Password for newly created demo accounts (after `check_allowed`)."""
    if settings.DEBUG:
        return DEV_PASSWORD
    check_allowed(command, options)
    password = os.environ.get(PASSWORD_ENV, '').strip()
    if len(password) < MIN_PASSWORD_LENGTH or password == DEV_PASSWORD:
        raise CommandError(
            f'{command} {FLAG} needs {PASSWORD_ENV}: a password of at least {MIN_PASSWORD_LENGTH} '
            f'characters for the demo accounts (never the development password).'
        )
    return password
