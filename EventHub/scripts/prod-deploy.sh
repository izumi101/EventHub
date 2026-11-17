#!/usr/bin/env bash
# Deploy or update EventHub on the production VM (docs/DEPLOY.md).
#
#   scripts/prod-deploy.sh                # pull, build, start, migrate, check
#   scripts/prod-deploy.sh --seed-demo    # ... then load the demo accounts and showcase events
#   scripts/prod-deploy.sh --no-pull      # deploy the checkout as it is
#
# Run as the deploy user from the repository checkout (no sudo; the user is
# in the docker group). Steps:
#   1. refuse to run while .env has TODO markers or missing required values
#   2. git pull --ff-only (remembers the previous commit for a rollback)
#   3. build images, up -d --wait (the backend entrypoint migrates as the owner)
#   4. migrate + setup_db_roles (owner, idempotent), verify_db_roles, db_schemas --check
#   5. https://SITE_DOMAIN/api/health/ through Caddy
set -euo pipefail
cd "$(dirname "$0")/.."

SEED_DEMO=0
PULL=1
for arg in "$@"; do
  case "$arg" in
    --seed-demo) SEED_DEMO=1 ;;
    --no-pull) PULL=0 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
manage() { "${COMPOSE[@]}" exec -T backend python manage.py "$@"; }
step() { printf '\n==> %s\n' "$1"; }
env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }

step "Checking .env"
[ -f .env ] || { echo "No .env: run scripts/prod-env.sh first." >&2; exit 1; }
if [ "$(stat -c %a .env 2>/dev/null || stat -f %Lp .env)" != 600 ]; then
  chmod 600 .env
  echo "Fixed .env permissions to 600."
fi
missing=()
for var in SITE_DOMAIN PAY_DOMAIN DJANGO_SECRET_KEY POSTGRES_PASSWORD POSTGRES_APP_PASSWORD \
  POSTGRES_READONLY_PASSWORD MFA_ENCRYPTION_KEY FREEDOMPAY_MERCHANT_ID FREEDOMPAY_SECRET_KEY \
  FPAY_CONTROL_TOKEN EMAIL_HOST_USER EMAIL_HOST_PASSWORD; do
  [ -n "$(env_value "$var")" ] || missing+=("$var")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Fill in these values in .env first: ${missing[*]}" >&2
  exit 1
fi
if [ -n "$(env_value CADDY_LOCAL_CERTS)" ] || [ -n "$(env_value PUBLIC_URL_PORT)" ]; then
  echo "CADDY_LOCAL_CERTS / PUBLIC_URL_PORT are for local testing only; empty them on a server." >&2
  exit 1
fi
SITE_DOMAIN=$(env_value SITE_DOMAIN)
"${COMPOSE[@]}" config -q

PREVIOUS=$(git rev-parse HEAD)
if [ "$PULL" = 1 ]; then
  step "Updating the checkout"
  git pull --ff-only
fi
CURRENT=$(git rev-parse HEAD)
echo "Deploying $(git log -1 --format='%h %s') (previous: ${PREVIOUS:0:7})"

step "Building images"
"${COMPOSE[@]}" build --pull

step "Starting the stack"
# A running worker of the previous release would keep its old connections
# through the migration (docs/DATABASE_SCHEMAS.md); stop it first.
"${COMPOSE[@]}" stop worker 2>/dev/null || true
"${COMPOSE[@]}" up -d --remove-orphans --wait --wait-timeout 600

step "Database: migrations and roles (as the schema owner)"
manage migrate --noinput
manage setup_db_roles
manage verify_db_roles | tail -n 3
manage db_schemas --check

if [ "$SEED_DEMO" = 1 ]; then
  step "Demo data (DJANGO_DEBUG stays 0)"
  [ -n "$(env_value DJANGO_SEED_DEMO_PASSWORD)" ] || { echo "Set DJANGO_SEED_DEMO_PASSWORD in .env." >&2; exit 1; }
  [ -n "$(env_value DJANGO_SEED_ADMIN_PASSWORD)" ] || { echo "Set DJANGO_SEED_ADMIN_PASSWORD in .env." >&2; exit 1; }
  manage seed_data --noinput --accounts-only --i-know-this-is-a-demo
  manage seed_showcase --i-know-this-is-a-demo
  manage index_events || echo "index_events failed (search falls back to keywords); re-run it later."
fi

step "Health check through Caddy"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 10 "https://${SITE_DOMAIN}/api/health/" >/dev/null 2>&1; then ok=1; break; fi
  sleep 5
done
"${COMPOSE[@]}" ps --format 'table {{.Name}}\t{{.Status}}'
if [ "$ok" != 1 ]; then
  echo "https://${SITE_DOMAIN}/api/health/ did not answer 200 (certificate still being issued? DNS?)." >&2
  echo "Logs: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 100 caddy backend" >&2
  echo "Rollback: git checkout ${PREVIOUS} && scripts/prod-deploy.sh --no-pull   (see docs/DEPLOY.md)" >&2
  exit 1
fi

echo
echo "Deployed ${CURRENT:0:7}: https://${SITE_DOMAIN}/ is healthy."
if [ "$PREVIOUS" != "$CURRENT" ]; then
  echo "Rollback if needed: git checkout ${PREVIOUS} && scripts/prod-deploy.sh --no-pull"
  echo "(code only; a release that changed the schema needs a restore, docs/DEPLOY.md)"
fi
