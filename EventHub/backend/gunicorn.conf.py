"""Gunicorn settings for the ASGI app (REST API + seat-map WebSockets).

Gunicorn supervises uvicorn worker processes: a crashed worker is replaced,
and a deploy (SIGTERM) lets in-flight requests finish within
`graceful_timeout`. Open WebSockets are closed with code 1012 ("service
restart"); the SPA reconnects with backoff. Broadcasts reach every worker
through the Redis channel layer, so any number of workers can serve sockets.
"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
worker_class = 'eventhub_backend.uvicorn_worker.EventHubUvicornWorker'

# One async worker per CPU handles many concurrent connections; scale out
# with more containers/pods rather than more workers per container.
workers = int(os.environ.get('WEB_CONCURRENCY', multiprocessing.cpu_count()))

timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))
graceful_timeout = int(os.environ.get('GUNICORN_GRACEFUL_TIMEOUT', '30'))
keepalive = 5

# No max_requests recycling: restarting a worker would drop its open
# WebSockets mid-event.

accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# X-Forwarded-For is read by DRF with NUM_PROXIES (see settings); uvicorn
# must not rewrite the client address from headers of untrusted peers.
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')
