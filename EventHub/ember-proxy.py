#!/usr/bin/env python3
"""Tiny static+API proxy for previewing the built Ember frontend with live data.
Serves dist/browser; forwards /api, /media, /static to the Django backend on :8000."""
import os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(__file__), 'frontend', 'dist', 'eventhub-frontend', 'browser')
BACKEND = 'http://localhost:8000'
PROXY_PREFIXES = ('/api', '/media', '/static', '/ws')

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _proxy(self):
        url = BACKEND + self.path
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
            body = self.rfile.read(length) if length else None
            req = urllib.request.Request(url, method=self.command, data=body)
            for h in ('Content-Type', 'Authorization', 'X-CSRFToken', 'Cookie'):
                if self.headers.get(h):
                    req.add_header(h, self.headers.get(h))
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                self.send_response(r.status)
                self.send_header('Content-Type', r.headers.get('Content-Type', 'application/json'))
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', e.headers.get('Content-Type', 'application/json'))
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(502); self.end_headers(); self.wfile.write(str(e).encode())

    def _static(self):
        path = self.path.split('?', 1)[0]
        fp = os.path.join(ROOT, path.lstrip('/'))
        if not os.path.isfile(fp):
            fp = os.path.join(ROOT, 'index.html')  # SPA fallback
        ctype = 'text/html'
        if fp.endswith('.js'): ctype = 'text/javascript'
        elif fp.endswith('.css'): ctype = 'text/css'
        elif fp.endswith('.woff2'): ctype = 'font/woff2'
        elif fp.endswith('.png'): ctype = 'image/png'
        elif fp.endswith('.svg'): ctype = 'image/svg+xml'
        elif fp.endswith('.ico'): ctype = 'image/x-icon'
        elif fp.endswith('.json'): ctype = 'application/json'
        try:
            with open(fp, 'rb') as f: body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(404); self.end_headers(); self.wfile.write(str(e).encode())

    def do_GET(self):
        if self.path.startswith(PROXY_PREFIXES):
            self._proxy()
        else:
            self._static()

    def do_POST(self):   self._proxy()
    def do_PUT(self):    self._proxy()
    def do_PATCH(self):  self._proxy()
    def do_DELETE(self): self._proxy()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8767'))
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
