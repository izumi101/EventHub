#!/usr/bin/env bash
# Nightly PostgreSQL backup of the EventHub app database (docs/DEPLOY.md, "Backups").
#
#   scripts/prod-backup.sh                 # dump to /var/backups/eventhub, keep the last 7
#   BACKUP_DIR=/mnt/x KEEP=14 scripts/prod-backup.sh
#
# pg_dump -Fc runs inside the db container as the schema owner (it carries
# every domain schema, the roles' grants and the data); the dump is checked
# with pg_restore -l before older dumps are pruned. Run by the
# eventhub-backup.timer systemd unit (scripts/install-backup-timer.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-/var/backups/eventhub}"
KEEP="${KEEP:-7}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }
DB=$(env_value POSTGRES_DB); DB=${DB:-eventhub}
OWNER=$(env_value POSTGRES_USER); OWNER=${OWNER:-eventhub_user}

umask 077
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$BACKUP_DIR/eventhub-${stamp}.dump"
partial="${target}.partial"
trap 'rm -f "$partial"' EXIT

# Local socket inside the container: no password on the command line.
"${COMPOSE[@]}" exec -T db pg_dump -U "$OWNER" -d "$DB" -Fc --no-password > "$partial"

# Verify: the archive's table of contents must be readable and non-trivial.
entries=$("${COMPOSE[@]}" exec -T db pg_restore -l < "$partial" | grep -c ' TABLE DATA ' || true)
if [ "$entries" -lt 10 ]; then
  echo "Backup verification failed: only $entries TABLE DATA entries in $partial" >&2
  exit 1
fi
mv "$partial" "$target"
trap - EXIT

# Keep the newest $KEEP dumps (names are our own timestamps: ls is safe).
# shellcheck disable=SC2012
mapfile -t old < <(ls -1t "$BACKUP_DIR"/eventhub-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))")
if [ ${#old[@]} -gt 0 ]; then
  rm -f -- "${old[@]}"
fi

size=$(du -h "$target" | cut -f1)
echo "Backup OK: $target ($size, $entries tables with data); kept the newest $KEEP."
