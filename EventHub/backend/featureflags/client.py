"""The process-local Unleash client.

One client per OS process, created on first use and never at import time.
Gunicorn forks its workers, and the SDK keeps its flag state fresh from an
APScheduler background thread — threads don't survive a fork, so a client
inherited from a parent process would silently stop polling. A fork hook
drops the inherited client (and lock) in the child, and the client also
remembers the PID that created it, so any other process builds its own.

Nothing here blocks a request on the network: registration and the first
fetch run on a background thread, and until they succeed every flag answers
with its registry default. Flag state lives in process memory only (the
SDK's default file cache is shared between processes on disk and races).
"""

import atexit
import contextlib
import logging
import os
import socket
import threading
import time

from django.conf import settings
from UnleashClient import UnleashClient
from UnleashClient.cache import BaseCache
from UnleashClient.constants import FEATURES_URL
from UnleashClient.utils import InstanceAllowType

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_client: UnleashClient | None = None
_client_pid: int | None = None
_init_thread: threading.Thread | None = None
# A client that couldn't even be constructed is not retried on every flag
# lookup; the process keeps answering with defaults (and says so once).
_failed_pid: int | None = None
_atexit_registered = False


class MemoryCache(BaseCache):
    """Per-process, in-memory flag state for the SDK."""

    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def mset(self, data):
        with self._lock:
            self._data.update(data)

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def exists(self, key):
        with self._lock:
            return key in self._data

    def destroy(self):
        with self._lock:
            self._data.clear()


def _make_cache() -> BaseCache:
    return MemoryCache()


def _build_client(cache: BaseCache) -> UnleashClient:
    return UnleashClient(
        url=settings.UNLEASH_URL,
        app_name=settings.UNLEASH_APP_NAME,
        environment=settings.UNLEASH_ENVIRONMENT,
        # Shown in the Unleash UI (Applications): which pod/process is polling.
        instance_id=f'{socket.gethostname()}:{os.getpid()}',
        refresh_interval=settings.UNLEASH_REFRESH_INTERVAL,
        metrics_interval=settings.UNLEASH_METRICS_INTERVAL,
        request_timeout=settings.UNLEASH_REQUEST_TIMEOUT,
        # The next poll is the retry; in-request retries only add log noise.
        request_retries=0,
        custom_headers={'Authorization': settings.UNLEASH_API_TOKEN},
        cache=cache,
        # This module guarantees one client per process; the SDK's own
        # duplicate detection would warn after every fork.
        multiple_instance_mode=InstanceAllowType.SILENTLY_ALLOW,
    )


def _initialize(client: UnleashClient, cache: BaseCache) -> None:
    """Registration, first fetch, then the polling and metrics jobs."""
    started = time.monotonic()
    try:
        client.initialize_client()
    except Exception:
        # Only a malformed UNLEASH_URL gets here (network errors are retried
        # by the polling job). Flags keep answering with their defaults.
        logger.exception('Unleash client failed to start; feature flags use their defaults')
        return
    if cache.exists(FEATURES_URL):
        logger.info(
            'Feature flags loaded from Unleash in %.1fs (url=%s, app=%s, environment=%s)',
            time.monotonic() - started,
            settings.UNLEASH_URL,
            settings.UNLEASH_APP_NAME,
            settings.UNLEASH_ENVIRONMENT,
        )
    else:
        logger.warning(
            'Unleash at %s is not answering; feature flags use their defaults until it does (retrying every %ss)',
            settings.UNLEASH_URL,
            settings.UNLEASH_REFRESH_INTERVAL,
        )


def _shutdown_at_exit() -> None:
    # The interpreter is exiting: stop the polling thread, report nothing.
    with contextlib.suppress(Exception):
        reset_client()


def get_client() -> UnleashClient | None:
    """This process's client, or None when Unleash is off or unusable."""
    global _client, _client_pid, _init_thread, _failed_pid, _atexit_registered

    if not settings.UNLEASH_ENABLED:
        return None
    pid = os.getpid()
    client = _client
    if client is not None and _client_pid == pid:
        return client
    if _failed_pid == pid:
        return None

    with _lock:
        if _client is not None and _client_pid == pid:
            return _client
        if _failed_pid == pid:
            return None
        # A client inherited across fork() has no polling thread in this
        # process; drop it without touching its (parent's) scheduler.
        _client = None
        cache = _make_cache()
        try:
            client = _build_client(cache)
        except Exception:
            _failed_pid = pid
            logger.exception('Could not create the Unleash client; feature flags use their defaults')
            return None
        _client, _client_pid = client, pid
        _init_thread = threading.Thread(target=_initialize, args=(client, cache), name='unleash-init', daemon=True)
        _init_thread.start()
        if not _atexit_registered:
            atexit.register(_shutdown_at_exit)
            _atexit_registered = True
        return client


def _after_fork_in_child() -> None:
    # The child must not inherit a lock some parent thread held at fork()
    # time, nor the parent's client (its polling thread stayed behind).
    global _lock, _client, _client_pid, _init_thread, _failed_pid
    _lock = threading.Lock()
    _client = _client_pid = _init_thread = _failed_pid = None


os.register_at_fork(after_in_child=_after_fork_in_child)


def wait_until_started(timeout: float | None = None) -> bool:
    """Block until this process's client finished its first fetch attempt.
    For management commands and tests; request code never waits."""
    thread = _init_thread
    if thread is None:
        return False
    thread.join(timeout)
    return not thread.is_alive()


def reset_client() -> None:
    """Stop this process's client (if any) and forget it."""
    global _client, _client_pid, _init_thread, _failed_pid

    with _lock:
        client, owner_pid, thread = _client, _client_pid, _init_thread
        _client = _client_pid = _init_thread = _failed_pid = None
    if client is None or owner_pid != os.getpid():
        return
    if thread is not None:
        thread.join(settings.UNLEASH_REQUEST_TIMEOUT * 4)
    client.destroy()
