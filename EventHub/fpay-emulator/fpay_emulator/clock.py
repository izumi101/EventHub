"""Virtual clock: real UTC time plus a persisted offset (``POST /_emulator/clock``).

Lifetimes, retry schedules, auto-capture and the refund window all read this
clock, so tests can jump hours ahead without waiting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .store import Store

_KEY = 'clock_offset_seconds'


class Clock:
    def __init__(self, store: Store) -> None:
        self._store = store
        self._offset = float(store.get_meta(_KEY, '0') or 0)

    @property
    def offset_seconds(self) -> float:
        return self._offset

    def now(self) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=self._offset)

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError('the clock only moves forward')
        self._offset += seconds
        self._store.set_meta(_KEY, repr(self._offset))

    def reload(self) -> None:
        self._offset = float(self._store.get_meta(_KEY, '0') or 0)
