"""Who may run the demo seed commands (`seed_data`, `seed_showcase`, `seed_demo_kz`).

Demo content is for development (`DJANGO_DEBUG=1`), where the demo accounts
use the documented password `password123`. A public demo deployment runs with
`DJANGO_DEBUG=0` and may load the same content only when the operator says so
explicitly (`--i-know-this-is-a-demo`), and then never with a publicly known
password:

- `seed_data` and `seed_showcase` give their accounts `DJANGO_SEED_DEMO_PASSWORD`
  from the server's `.env` (docs/DEPLOY.md, "Demo data");
- `seed_demo_kz` creates hundreds of accounts and gives each its own random
  password, written only to a new `--credentials-file` (mode 0600) and never
  to stdout, stderr or a log (docs/DEMO_DATA.md).

The accounts of `seed_demo_kz` use the undeliverable domain `DEMO_EMAIL_DOMAIN`:
`notifications.service.notify` keeps the in-app notification but queues no
email for such an address, so the worker never mails them through the
deployment's real SMTP account.
"""

import concurrent.futures
import multiprocessing
import os
import secrets
import string
import time

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

FLAG = '--i-know-this-is-a-demo'
CREDENTIALS_OPTION = '--credentials-file'
PASSWORD_ENV = 'DJANGO_SEED_DEMO_PASSWORD'  # noqa: S105 - the variable's name, not a password
DEV_PASSWORD = 'password123'  # noqa: S105 - documented development password, DEBUG only
MIN_PASSWORD_LENGTH = 12

# Accounts of seed_demo_kz: never deliverable (".local" is reserved for local use).
DEMO_EMAIL_DOMAIN = 'demo.eventhub.local'

GENERATED_PASSWORD_LENGTH = 20
_UPPER = string.ascii_uppercase
_LOWER = string.ascii_lowercase
_DIGITS = string.digits
# No whitespace, quotes or backslash: the password survives a shell and a TSV file.
_SYMBOLS = '!@#$%^&*-_=+?'

# Hashing one password takes a fraction of a second with the production hasher;
# a process pool pays off only when the whole batch would take longer than this.
POOL_THRESHOLD_SECONDS = 2.0
MAX_HASH_WORKERS = 8


def add_demo_flag(parser) -> None:
    parser.add_argument(
        FLAG,
        action='store_true',
        dest='demo_deployment',
        help=(
            'Allow demo content with DJANGO_DEBUG=0 (a public demo deployment). Demo accounts then get '
            'a password that is not the development password (see the command help).'
        ),
    )


def is_demo_address(email: str) -> bool:
    """True for an address of the seed_demo_kz accounts (never delivered)."""
    return (email or '').strip().lower().endswith(f'@{DEMO_EMAIL_DOMAIN}')


def check_allowed(command: str, options: dict, *, needs: str | None = None) -> None:
    """Raise CommandError unless demo content may be created here.

    `needs` names what the command also requires on a DEBUG=0 deployment
    (default: the `DJANGO_SEED_DEMO_PASSWORD` variable)."""
    if settings.DEBUG:
        return
    if not options.get('demo_deployment'):
        needs = needs or f'{PASSWORD_ENV} set'
        raise CommandError(
            f'{command} creates demo content; run it only with DJANGO_DEBUG=1, or on a public demo '
            f'deployment with {FLAG} and {needs} (docs/DEPLOY.md).'
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


# ── Per-account random passwords (seed_demo_kz on DEBUG=0) ──


def generate_password() -> str:
    """A random 20-character password with upper and lower case letters, digits
    and symbols that passes the deployment's password validators."""
    alphabet = _UPPER + _LOWER + _DIGITS + _SYMBOLS
    for _ in range(50):
        chars = [secrets.choice(_UPPER), secrets.choice(_LOWER), secrets.choice(_DIGITS), secrets.choice(_SYMBOLS)]
        chars += [secrets.choice(alphabet) for _ in range(GENERATED_PASSWORD_LENGTH - len(chars))]
        secrets.SystemRandom().shuffle(chars)
        password = ''.join(chars)
        try:
            validate_password(password)
        except ValidationError:
            continue
        return password
    raise CommandError('Could not generate a password that passes the password validators.')


def open_credentials_file(path: str):
    """Create `path` (mode 0600, never overwriting) and return it open for writing.

    Raises CommandError when the file exists or cannot be created: the
    passwords of an earlier run must not be lost to a silent overwrite."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise CommandError(
            f'{path} already exists; choose a new --credentials-file (an existing file is never overwritten).'
        ) from None
    except OSError as exc:
        raise CommandError(f'Cannot create {path}: {exc.strerror or exc}') from None
    return os.fdopen(fd, 'w', encoding='utf-8')


def write_credentials(handle, rows) -> int:
    """Write `username<TAB>password<TAB>role` lines and flush them to disk."""
    count = 0
    for username, password, role in rows:
        handle.write(f'{username}\t{password}\t{role}\n')
        count += 1
    handle.flush()
    os.fsync(handle.fileno())
    return count


def _hash_one(password: str) -> str:
    return make_password(password)


def _pool_context():
    methods = multiprocessing.get_all_start_methods()
    return multiprocessing.get_context('fork' if 'fork' in methods else 'spawn')


def hash_passwords(passwords, *, progress=None, workers: int | None = None) -> list[str]:
    """`make_password` of each password (every one with its own salt).

    The first password is hashed here and timed: when the whole batch is
    cheap (a test hasher) it stays sequential; otherwise the rest goes through
    a process pool, falling back to sequential hashing when no pool can start.
    `progress(done, total)` is called every 100 passwords."""
    passwords = list(passwords)
    total = len(passwords)
    if total == 0:
        return []
    started = time.monotonic()
    hashes = [_hash_one(passwords[0])]
    per_password = time.monotonic() - started
    if progress:
        progress(1, total)

    rest = passwords[1:]
    workers = workers or min(os.cpu_count() or 1, MAX_HASH_WORKERS)
    # A daemonic process (a parallel test worker) may not have children: hash in place.
    can_fork = not multiprocessing.current_process().daemon
    if rest and can_fork and workers > 1 and per_password * len(rest) > POOL_THRESHOLD_SECONDS:
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=_pool_context()) as pool:
                for done, hashed in enumerate(pool.map(_hash_one, rest, chunksize=8), start=2):
                    hashes.append(hashed)
                    if progress and done % 100 == 0:
                        progress(done, total)
            rest = []
        except Exception:  # no pool can start here (a daemonic process, a sandbox): hash one by one
            hashes = hashes[:1]  # no pool here: start the rest over, one by one
    for done, password in enumerate(rest, start=len(hashes) + 1):
        hashes.append(_hash_one(password))
        if progress and done % 100 == 0:
            progress(done, total)
    if progress and total % 100:
        progress(total, total)
    return hashes
