# Production deployment (one VM, Docker Compose)

## Agent Entry

- Purpose: how EventHub runs on a single VM: first deploy, updates, domain switch, backups, logs, budget, security.
- Read when: deploying, updating or operating the production VM.
- Canonical: Yes. Files: `docker-compose.prod.yml`, `deploy/Caddyfile`, `deploy/nginx-behind-proxy.conf`, `deploy/env.production.example`, `scripts/server-bootstrap.sh`, `scripts/prod-env.sh`, `scripts/prod-deploy.sh`, `scripts/prod-backup.sh`, `scripts/install-backup-timer.sh`.
- Related: `DATABASE_ROLES.md`, `DATABASE_SCHEMAS.md`, `SECURITY_2FA.md`, `NOTIFICATIONS.md`, `DEMO.md`.

## Target

One Azure VM (region India South Central): Ubuntu 24.04 x86_64, 2 vCPU, 7.7 GiB RAM, 61 GB disk, sudo user `eventhub`, SSH keys only. No managed services: PostgreSQL, Redis and everything else run as containers. Demo mode: `DJANGO_DEBUG=0`, KZT payments through the Freedom Pay **emulator** (no real acquirer, no real money), email through Gmail SMTP.

## Architecture

```text
Internet ──80/443 tcp, 443 udp──> ufw ──> caddy (only published ports; Let's Encrypt, HSTS, zstd/gzip, JSON access log)
                                           │
              https://SITE_DOMAIN ─────────┤──> frontend:80  nginx: Angular SPA, /media (volume), proxies:
                                           │        ├── /api/, /static/ ──> backend:8000  gunicorn + uvicorn workers (REST)
                                           │        └── /ws/  (WebSocket) ──> backend:8000  (Channels, seat map)
              https://PAY_DOMAIN ──────────┘──> fpay-emulator:8080  only /pay.html, /pay/*, /static/*
                                                        (merchant API and /_emulator are not routed)

compose network (no host ports):
  backend ──> db:5432 (PostgreSQL 16 + pgvector; owner for migrate, eventhub_app at runtime)
          ──> redis:6379 (channel layer, throttling, cache)
          ──> fpay-emulator:8080 (init_payment, get_status3, refunds)
  fpay-emulator ──> http://backend:8000/api/v1/payments/callback/freedompay/ (signed result callbacks)
  worker (run_worker: outbox emails via Gmail SMTP, webhooks, search indexing, maintenance) ──> db, redis
  [profile flags] unleash ──> unleash-db

host: /var/backups/eventhub  <── eventhub-backup.timer (02:30 UTC, pg_dump -Fc, keep 7)
```

Client address and scheme: Caddy overwrites `X-Forwarded-For`/`-Proto` with what it saw; nginx (`deploy/nginx-behind-proxy.conf`) trusts that hop (`real_ip`) and forwards one `X-Forwarded-For` entry and `X-Forwarded-Proto: https` to Django, which trusts exactly one proxy (`DJANGO_NUM_PROXIES=1`). Per-client rate limits therefore work behind both proxies.

## First deploy

All commands run on the VM as `eventhub`, unless marked `sudo`.

1. **Azure network security group:** allow inbound 22/tcp (ideally only from your IP), 80/tcp, 443/tcp, 443/udp.
2. **Clone and bootstrap** (Docker, ufw, swap, unattended upgrades, sshd hardening, fail2ban, backup timer):

   ```bash
   git clone https://github.com/izumi101/EventHub.git ~/EventHub
   sudo ~/EventHub/EventHub/scripts/server-bootstrap.sh --user eventhub --repo ~/EventHub
   exit   # log in again so the docker group applies
   ```

   The script prints what it changed; run it again any time (idempotent). It disables SSH passwords only if `~eventhub/.ssh/authorized_keys` holds a key. Reboot if it says so.
3. **Create `.env`** with fresh secrets (it asks for the SMTP login, the Gmail app password and the admin password; Enter skips and leaves a TODO):

   ```bash
   cd ~/EventHub/EventHub
   scripts/prod-env.sh                      # SITE_DOMAIN = <public-ip-with-dashes>.sslip.io
   ```

   `.env` is mode 600 and never printed. The script refuses to overwrite an existing `.env`.
4. **Fill in SMTP** (if skipped): `nano .env` → `EMAIL_HOST_USER=<you>@gmail.com`, `EMAIL_HOST_PASSWORD=<16-character app password>` (Google Account → Security → 2-Step Verification → App passwords), `DEFAULT_FROM_EMAIL=EventHub <<you>@gmail.com>`, `DJANGO_SEED_ADMIN_PASSWORD=<strong password>`; delete the `# TODO(owner)` lines. Compose refuses to start while the SMTP values are empty.
5. **Deploy and load the demo:**

   ```bash
   scripts/prod-deploy.sh --seed-demo
   ```

   It builds the images (first build ~10–15 min: PyTorch for semantic search), starts the stack with `--wait`, runs `migrate` and `setup_db_roles` as the owner, `verify_db_roles`, `db_schemas --check`, then the demo seed, and checks `https://SITE_DOMAIN/api/health/` through Caddy. Let's Encrypt issues both certificates on the first request (needs ports 80/443 open).
6. **Admin:** with `--seed-demo` the `admin` superuser has `DJANGO_SEED_ADMIN_PASSWORD`. Without demo data: `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python manage.py createsuperuser`. The admin (and organizers) must enroll 2FA at the first sign-in (`SECURITY_2FA.md`); email codes arrive through Gmail.
7. **Check:** open `https://SITE_DOMAIN/`, sign in as `attendee` (password: `grep DEMO_PASSWORD .env`), buy a ticket for a KZT event, pay on `https://PAY_DOMAIN/...` with **Pay (success)**; the e-ticket email arrives.

Tip: `alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'` in `~/.bashrc`; the commands below use it.

## Demo data

`--seed-demo` runs, with `DJANGO_DEBUG=0`:

- `seed_data --accounts-only --i-know-this-is-a-demo`: `admin` (`DJANGO_SEED_ADMIN_PASSWORD`), `organizer` and `attendee` (`DJANGO_SEED_DEMO_PASSWORD`, generated by `prod-env.sh`, never `password123`; the commands refuse the development password and the public test TOTP secret);
- `seed_showcase --i-know-this-is-a-demo`: the showcase events, without the paid USD ones (Stripe is not enabled, they could not be sold);
- `index_events`: search embeddings.

All three are idempotent. `seed_demo_kz` stays development-only on purpose: 600 accounts with a shared password on undeliverable `*.eventhub.local` addresses would make the worker send reminders through the Gmail account (500 emails/day limit).

## Switching from sslip.io to a real domain

1. DNS: `A` records for `example.kz` and `pay.example.kz` → the VM's IP (wait until `dig +short example.kz` answers).
2. `.env`: `SITE_DOMAIN=example.kz`, `PAY_DOMAIN=pay.example.kz` (optionally `ACME_EMAIL`).
3. `scripts/prod-deploy.sh --no-pull`. Caddy gets the new certificates; allowed hosts, CORS/CSRF origins, `FRONTEND_URL`, WebAuthn and the emulator's public URL follow `SITE_DOMAIN`.
4. Consequences: passkeys registered on the sslip.io name stop working (the WebAuthn RP ID changed; users sign in with another factor and register a new passkey); links in emails already sent point to the old name.
5. Once the domain is final, consider `includeSubDomains; preload` in the HSTS header of `deploy/Caddyfile` (hard to undo; never on sslip.io).

## Updating

```bash
cd ~/EventHub/EventHub
scripts/prod-backup.sh          # fresh dump before every update
scripts/prod-deploy.sh          # git pull --ff-only, build, up --wait, migrate, checks
```

The worker is stopped before the new release starts so it never runs old code against migrated tables (`DATABASE_SCHEMAS.md`). WebSockets reconnect by themselves after the backend restarts.

**Rollback** (the script prints the previous commit): code-only releases: `git checkout <previous> && scripts/prod-deploy.sh --no-pull`. A release whose migrations changed the schema: restore the dump taken before the update (below), then deploy the previous commit. Return to the branch afterwards with `git checkout main`.

## Backups and restore

`eventhub-backup.timer` (installed by the bootstrap, or `sudo scripts/install-backup-timer.sh`) runs `scripts/prod-backup.sh` every night at 02:30 UTC: `pg_dump -Fc` of the app database as the owner (all domain schemas, grants and data) to `/var/backups/eventhub/eventhub-<UTC>.dump`, verified with `pg_restore -l`, newest 7 kept.

```bash
systemctl list-timers eventhub-backup.timer
journalctl -u eventhub-backup --since today
sudo systemctl start eventhub-backup        # run one now
```

**Off-site copy:** the dumps live on the VM's disk; copy them elsewhere regularly (e.g. `scp eventhub@<vm>:/var/backups/eventhub/*.dump .`, or an Azure Storage container with `azcopy`). Media uploads (`backend_media` volume) are not in the dump: `docker run --rm -v eventhub_backend_media:/m -v /var/backups/eventhub:/b alpine tar czf /b/media-$(date -u +%F).tgz -C /m .`

**Restore** (replaces all data):

```bash
cd ~/EventHub/EventHub
DUMP=/var/backups/eventhub/eventhub-<stamp>.dump
dc stop backend worker caddy
dc exec -T db psql -U eventhub_user -d postgres -c "DROP DATABASE eventhub WITH (FORCE)" -c "CREATE DATABASE eventhub OWNER eventhub_user"
dc exec -T db pg_restore -U eventhub_user -d eventhub --no-owner --role=eventhub_user < "$DUMP"
dc up -d --wait          # entrypoint: migrate (writes the database search_path again) + setup_db_roles
dc exec backend python manage.py verify_db_roles | tail -3
dc exec backend python manage.py db_schemas --check
```

`ALTER DATABASE ... SET search_path` is not part of a dump; the next `migrate` writes it again (`DATABASE_SCHEMAS.md`). Test a restore into a scratch database now and then: `CREATE DATABASE restore_test`, `pg_restore -d restore_test`, count rows, drop it.

## Logs

```bash
dc ps                                  # state and health of every service
dc logs -f --tail 100 backend worker   # app logs; caddy logs are JSON access logs
dc logs caddy | grep '"status":5'      # 5xx at the edge
docker stats --no-stream               # memory/CPU against the limits
```

Every service logs to Docker's `json-file` driver with rotation (10 MB × 5 files, compressed), so logs cannot fill the disk. 2FA audit events are in the backend log (`mfa` logger).

## Resource budget

Memory limits in `docker-compose.prod.yml` (ceilings, not reservations):

| Service | Limit | Notes |
|---|---|---|
| db | 1536M | `shared_buffers=384MB`, `effective_cache_size=1GB`, `work_mem=8MB`, `max_connections=100`, slow-query log > 1 s |
| backend | 2048M | `WEB_CONCURRENCY=2` uvicorn workers (one per vCPU), each loads the embedding model |
| worker | 1024M | loads the embedding model for indexing |
| redis | 256M | `maxmemory 200mb`, `noeviction`, no persistence |
| caddy | 256M | |
| fpay-emulator | 192M | |
| frontend | 128M | nginx |
| **total** | **5440M** | leaves ~2.2 GiB for the OS, page cache, dockerd + 2 GB swap |
| unleash + unleash-db (`flags`) | +768M | optional |

Disk: images ~6 GB (backend with PyTorch ~4.5 GB), logs ≤ 50 MB per service, dumps grow with the data. `INSTALL_SEMANTIC_SEARCH=0` in `.env` makes a slim image (~1 GB less RAM, keyword search only). Prune old images after updates: `docker image prune -f`.

## Security notes

- **Exposure:** only Caddy publishes ports; ufw allows 22/80/443 (Docker bypasses ufw for published ports, which is why nothing else is published). PostgreSQL, Redis, the backend, the emulator's merchant/control API and Unleash are reachable only inside the compose network.
- **Secrets:** `.env` (mode 600, never committed) is the only place; `prod-env.sh` generates them, `prod-deploy.sh` never prints them. Rotation of DB passwords: `DATABASE_ROLES.md`.
- **Database:** migrations run as the owner; gunicorn and the worker connect as `eventhub_app` (no DDL), reports as `eventhub_readonly` (`DATABASE_ROLES.md`). The prod overlay makes both role passwords mandatory.
- **Django:** `DJANGO_DEBUG=0` is forced by the overlay; the start-up guard refuses mock payments, console email, a missing `MFA_ENCRYPTION_KEY` and wildcard hosts. Secure cookies; HSTS (1 year, no preload) from Caddy; CSP and frame/nosniff headers from nginx.
- **2FA:** required for organizers, staff and superusers. For a real launch set `MFA_EMAIL_ALLOWED_FOR_REQUIRED_ROLES=0`.
- **Payments:** demo mode only (`FREEDOMPAY_DEMO_MODE=1`, emulator). A real acquirer needs `FREEDOMPAY_API_URL=https://api.freedompay.kz`, real keys, `FREEDOMPAY_DEMO_MODE=0` and an https `FREEDOMPAY_RESULT_URL` the gateway can reach (`https://SITE_DOMAIN/api/v1/payments/callback/freedompay/`).
- **Host:** key-only SSH, no root login, fail2ban (5 failures → 1 h ban), unattended security upgrades, UTC clock, containers with `no-new-privileges`.
- **Data residency:** this VM is in Azure **India South Central**: all personal data (accounts, tickets, emails) is stored in India. Kazakhstan's personal data law (On Personal Data and Their Protection, art. 12-2) requires the personal data of KZ citizens to be stored in databases located in Kazakhstan, and the roadmap chose Yandex Cloud kz1 for that reason. The app has no `LEGAL_DATA_LOCATION` setting and no privacy policy page yet (roadmap phase 3), so nothing in the UI states the location: until the move, keep this deployment a demo with test data and say in any privacy text that data is hosted in India.

## Feature flags (optional)

`COMPOSE_PROFILES=flags` and `UNLEASH_ENABLED=1` in `.env`, then `scripts/prod-deploy.sh --no-pull`. The admin UI has no public port; open it through an SSH tunnel to a temporary local forwarder:

```bash
docker run --rm -d --name unleash-tunnel --network eventhub_default -p 127.0.0.1:4242:4242 alpine/socat tcp-listen:4242,fork,reuseaddr tcp:unleash:4242
# on your laptop: ssh -L 4242:127.0.0.1:4242 eventhub@<vm>, then http://localhost:4242 (admin / UNLEASH_ADMIN_PASSWORD from .env)
docker stop unleash-tunnel
```

## Local test of the production stack

Run it as a separate compose project so it cannot touch a development stack. Container names are fixed in `docker-compose.yml`, so add a small override that renames them and maps Caddy to free ports (e.g. `ports: !override ["127.0.0.1:38081:80", "127.0.0.1:38443:443"]`), and use an env file with `SITE_DOMAIN=eventhub.localhost`, `PAY_DOMAIN=pay.eventhub.localhost`, `CADDY_LOCAL_CERTS=1` (Caddy's internal CA instead of Let's Encrypt) and `PUBLIC_URL_PORT=:38443`. `prod-deploy.sh` refuses those two testing variables on a server.

## Costs

The VM size (2 vCPU / 8 GiB, e.g. B2ms/D2s-class) dominates: roughly USD 60–90 a month pay-as-you-go plus the OS disk (~USD 5–10 for 64 GB Premium/Standard SSD), the public IP (~USD 4) and outbound traffic (first 100 GB/month free). Stop (deallocate) the VM when not demoing to pay only for the disk and IP. sslip.io, Let's Encrypt and Gmail SMTP are free. Off-site backups in Azure Blob Storage cost cents per month at this size. Check current prices in the Azure pricing calculator for the region.
