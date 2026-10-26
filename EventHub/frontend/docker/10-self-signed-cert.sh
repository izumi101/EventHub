#!/bin/sh
# nginx-image entrypoint hook: make sure a TLS certificate exists.
# Real certificates are mounted at /etc/nginx/certs (see docker-compose.yml);
# without them we generate a self-signed one so the HTTPS server can start.
set -e
CERT_DIR=/etc/nginx/certs
if [ ! -s "$CERT_DIR/server.crt" ] || [ ! -s "$CERT_DIR/server.key" ]; then
  echo "No TLS certificate in $CERT_DIR — generating a self-signed one for local use"
  mkdir -p "$CERT_DIR"
  openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
    -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" >/dev/null 2>&1
  chmod 600 "$CERT_DIR/server.key"
fi
