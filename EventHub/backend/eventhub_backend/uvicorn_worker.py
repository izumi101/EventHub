"""Gunicorn worker class running the ASGI app on uvicorn.

Django's ASGI handler does not implement the lifespan protocol, so it is
switched off instead of logging a warning on every worker start.
"""

from uvicorn_worker import UvicornWorker


class EventHubUvicornWorker(UvicornWorker):
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, 'lifespan': 'off'}
