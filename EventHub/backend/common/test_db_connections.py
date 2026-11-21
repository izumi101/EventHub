"""settings.py: database connections are not kept open between requests.

The backend runs as ASGI (gunicorn + uvicorn workers). Django runs a
request's sync code in a thread of its own there, so a persistent connection
(CONN_MAX_AGE > 0) is never reused or closed: on prod 96 of 97 PostgreSQL
slots were held by idle backend connections and sign-in failed with 500.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ConnMaxAgeTests(SimpleTestCase):
    def conn_max_age(self, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith(('POSTGRES_', 'DJANGO_DB_'))}
        base.update({'DJANGO_DEBUG': '1', 'POSTGRES_USER': 'owner_role', 'POSTGRES_PASSWORD': 'owner-pw'}, **env)
        code = (
            "import sys; sys.argv = ['gunicorn', 'eventhub_backend.asgi:application']; "
            'import eventhub_backend.settings as s; '
            "print(s.DATABASES['default']['CONN_MAX_AGE'])"
        )
        result = subprocess.run(  # noqa: S603 - fixed interpreter and code
            [sys.executable, '-c', code],
            cwd=Path(settings.BASE_DIR),
            env=base,
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.strip().splitlines()[-1])

    def test_connections_close_after_each_request_by_default(self):
        self.assertEqual(self.conn_max_age(), 0)

    def test_operator_can_still_override(self):
        self.assertEqual(self.conn_max_age(POSTGRES_CONN_MAX_AGE='30'), 30)
