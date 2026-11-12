#!/usr/bin/env bash
# Phone demo of the QR payment: make the stack reachable from other devices on the same network.
#
#   scripts/demo-lan.sh on [IP]   # detect (or use) this machine's LAN address and switch .env to it
#   scripts/demo-lan.sh off       # back to localhost only
#   scripts/demo-lan.sh status
#
# A QR code holds the payment page address. With the defaults it is http://localhost:18080, which a phone
# resolves to itself, and the emulator only listens on 127.0.0.1. "on" points FPAY_PUBLIC_URL and
# FRONTEND_URL at the LAN address, publishes the emulator on all interfaces (behind FPAY_CONTROL_TOKEN),
# allows the address in DJANGO_ALLOWED_HOSTS and recreates the affected containers.
# Open the site on the laptop through the same LAN address, so the return from the payment page keeps you
# signed in. Demo only: never on a server.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=.env
[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE here (copy .env.example first)." >&2; exit 1; }

get_var() { python3 - "$ENV_FILE" "$1" <<'PY'
import re, sys
path, key = sys.argv[1], sys.argv[2]
for line in open(path, encoding='utf-8'):
    m = re.match(rf'\s*{re.escape(key)}=(.*)', line)
    if m:
        print(m.group(1).strip())
        break
PY
}

set_var() { python3 - "$ENV_FILE" "$1" "$2" <<'PY'
import re, sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding='utf-8').read()
line = f'{key}={value}'
pattern = rf'(?m)^\s*{re.escape(key)}=.*$'
if re.search(pattern, text):
    text = re.sub(pattern, lambda _: line, text, count=1)
else:
    text = text.rstrip('\n') + '\n' + line + '\n'
open(path, 'w', encoding='utf-8').write(text)
PY
}

detect_ip() {
  local ip=''
  if command -v ipconfig >/dev/null 2>&1; then          # macOS
    for iface in en0 en1 en2 en3 bridge100; do
      ip=$(ipconfig getifaddr "$iface" 2>/dev/null || true)
      [ -n "$ip" ] && break
    done
  fi
  if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then  # Linux
    ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
  fi
  echo "$ip"
}

hosts_without() { # $1 = hosts list, $2 = host to drop
  python3 -c "import sys; print(','.join(h for h in sys.argv[1].split(',') if h and h != sys.argv[2]))" "$1" "$2"
}

recreate() {
  docker compose up -d --wait fpay-emulator backend worker frontend
}

case "${1:-status}" in
  on)
    ip="${2:-$(detect_ip)}"
    if [ -z "$ip" ]; then echo 'Could not detect the LAN address; pass it: scripts/demo-lan.sh on 192.168.1.20' >&2; exit 1; fi
    old_ip=$(get_var DEMO_LAN_IP)
    hosts=$(get_var DJANGO_ALLOWED_HOSTS)
    hosts=${hosts:-localhost,127.0.0.1,backend}
    [ -n "$old_ip" ] && hosts=$(hosts_without "$hosts" "$old_ip")
    hosts="$(hosts_without "$hosts" "$ip"),$ip"
    set_var DEMO_LAN_IP "$ip"
    set_var DJANGO_ALLOWED_HOSTS "$hosts"
    set_var FRONTEND_URL "http://$ip:4200"
    set_var FPAY_PUBLIC_URL "http://$ip:18080"
    set_var FPAY_EMULATOR_BIND 0.0.0.0
    if [ -z "$(get_var FPAY_CONTROL_TOKEN)" ]; then
      set_var FPAY_CONTROL_TOKEN "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    fi
    recreate
    echo
    for url in "http://$ip:4200/" "http://$ip:18080/status/healthcheck"; do
      if curl -fsS -o /dev/null --max-time 5 "$url"; then echo "reachable: $url"; else echo "NOT reachable: $url" >&2; fi
    done
    echo
    echo "LAN demo is on. On this laptop open http://$ip:4200 (not localhost) and sign in there."
    echo "The phone must be on the same network. If the venue Wi-Fi isolates devices, share a hotspot from the phone."
    ;;
  off)
    old_ip=$(get_var DEMO_LAN_IP)
    hosts=$(get_var DJANGO_ALLOWED_HOSTS)
    [ -n "$old_ip" ] && [ -n "$hosts" ] && set_var DJANGO_ALLOWED_HOSTS "$(hosts_without "$hosts" "$old_ip")"
    set_var DEMO_LAN_IP ''
    set_var FRONTEND_URL http://localhost:4200
    set_var FPAY_PUBLIC_URL http://localhost:18080
    set_var FPAY_EMULATOR_BIND 127.0.0.1
    recreate
    echo 'LAN demo is off: the site is at http://localhost:4200 again.'
    ;;
  status)
    for key in DEMO_LAN_IP FRONTEND_URL FPAY_PUBLIC_URL FPAY_EMULATOR_BIND DJANGO_ALLOWED_HOSTS; do
      echo "$key=$(get_var "$key")"
    done
    echo "detected LAN address: $(detect_ip)"
    ;;
  *)
    echo 'usage: scripts/demo-lan.sh on [IP] | off | status' >&2
    exit 2
    ;;
esac
