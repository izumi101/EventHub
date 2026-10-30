"""Keeps an Unleash outage from flooding the log.

While Unleash is unreachable the SDK logs a failed fetch (with a traceback)
on every poll, in every worker process. This filter, attached to the
`UnleashClient` logger in settings.LOGGING, lets each distinct message
through once per interval and says how many repeats it dropped.
"""

import logging
import threading
import time


class RateLimitFilter(logging.Filter):
    # Some SDK messages embed the error text; bound the bookkeeping.
    MAX_TRACKED = 500

    def __init__(self, name='', interval=300.0):
        super().__init__(name)
        self.interval = float(interval)
        self._last_seen: dict[tuple[str, int], float] = {}
        self._suppressed: dict[tuple[str, int], int] = {}
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self._last_seen.clear()
            self._suppressed.clear()

    def filter(self, record):
        key = (str(record.msg), record.levelno)
        now = time.monotonic()
        with self._lock:
            last = self._last_seen.get(key)
            if last is not None and now - last < self.interval:
                self._suppressed[key] = self._suppressed.get(key, 0) + 1
                return False
            if len(self._last_seen) >= self.MAX_TRACKED:
                self._last_seen.clear()
                self._suppressed.clear()
            self._last_seen[key] = now
            suppressed = self._suppressed.pop(key, 0)
        if suppressed:
            record.msg = f'{record.msg} [{suppressed} similar messages suppressed]'
        return True
