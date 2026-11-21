#!/usr/bin/env bash
# Install the nightly backup as a systemd service + timer (idempotent).
#
#   sudo EventHub/scripts/install-backup-timer.sh [--user eventhub] [--repo /home/eventhub/EventHub]
#
# Runs scripts/prod-backup.sh as the deploy user at 02:30 UTC (randomised by
# up to 15 minutes, catches up after downtime). Logs: journalctl -u eventhub-backup
set -euo pipefail
DEPLOY_USER=eventhub
REPO_DIR=''
while [ $# -gt 0 ]; do
  case "$1" in
    --user) DEPLOY_USER="${2:?}"; shift 2 ;;
    --repo) REPO_DIR="${2:?}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
[ -n "$REPO_DIR" ] || REPO_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)/EventHub"
SCRIPT="$REPO_DIR/EventHub/scripts/prod-backup.sh"
[ -x "$SCRIPT" ] || { echo "Not found: $SCRIPT" >&2; exit 1; }

install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /var/backups/eventhub

service=$(cat <<EOF
[Unit]
Description=EventHub PostgreSQL backup (pg_dump -Fc, keep 7)
Wants=docker.service
After=docker.service

[Service]
Type=oneshot
User=$DEPLOY_USER
Group=$DEPLOY_USER
ExecStart=$SCRIPT
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
EOF
)
timer=$(cat <<'EOF'
[Unit]
Description=Nightly EventHub PostgreSQL backup

[Timer]
OnCalendar=*-*-* 02:30:00 UTC
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF
)
changed=0
write() { if [ "$(cat "$1" 2>/dev/null)" != "$2" ]; then printf '%s\n' "$2" > "$1"; changed=1; fi; }
write /etc/systemd/system/eventhub-backup.service "$service"
write /etc/systemd/system/eventhub-backup.timer "$timer"
if [ "$changed" = 1 ]; then
  systemctl daemon-reload
  echo "changed: installed eventhub-backup.service/.timer"
fi
systemctl enable --now eventhub-backup.timer >/dev/null
systemctl list-timers eventhub-backup.timer --no-pager | head -2
