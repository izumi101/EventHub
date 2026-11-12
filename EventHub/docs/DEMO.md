# Demo script

How to show EventHub end to end on one laptop, in demo mode: no real money moves. KZT tickets are paid through the Freedom Pay **emulator** (`fpay-emulator/`), other currencies through Stripe in mock mode.

## 1. Start the stack

```bash
cd EventHub
cp .env.example .env          # first time only; an existing .env needs the variables below
docker compose up -d --build --wait
```

An existing `.env` must contain the Freedom Pay demo block and (optionally) the database role passwords from `.env.example`:

- `PAYMENT_PROVIDERS_ENABLED=stripe,freedompay`, `FREEDOMPAY_API_URL=http://fpay-emulator:8080`, `FREEDOMPAY_MERCHANT_ID`, `FREEDOMPAY_SECRET_KEY`, `FREEDOMPAY_TESTING_MODE=1`, `FPAY_PUBLIC_URL=http://localhost:18080`. Compose refuses to start without `FREEDOMPAY_MERCHANT_ID` and `FREEDOMPAY_SECRET_KEY`.
- `POSTGRES_APP_PASSWORD` and `POSTGRES_READONLY_PASSWORD`: with them the backend and worker connect as the least-privilege `eventhub_app` role. Without them the app connects as the owner and logs a warning.

Services: site <http://localhost:4200>, API docs <http://localhost:4200/api/v1/docs/>, Freedom Pay emulator <http://localhost:18080>. Demo logins (seed data, `DJANGO_DEBUG=1` only): `attendee` / `password123`, `organizer` / `password123`.

Demo content: `seed_showcase` adds 18 hand-picked events in Almaty and Astana for `organizer` (15 in KZT, 2 in USD, free ones, seat maps, ticket tiers, one waiting for moderation) and no registrations, so the audience sees a clean catalogue and buys live. For volume (about 4 800 registrations, for the SQL checks) add `seed_demo_kz`. `index_events` builds the search embeddings. With `DJANGO_SEED_DATA=0` in `.env` a restart does not add the small default seed again.

```bash
docker compose exec backend python manage.py seed_showcase
docker compose exec backend python manage.py index_events
docker compose exec backend python manage.py seed_demo_kz      # optional, volume data
```

## 2. Full stack: backend, frontend, database

- Architecture: nginx (Angular SPA, proxy) → gunicorn with uvicorn workers (Django REST API and WebSockets) → PostgreSQL 16 + pgvector, Redis (channel layer, throttling, waiting room), outbox worker (emails, webhooks).
- Show: browse events, open an event with a seat map in two windows and take a seat in one — the other updates live over the WebSocket.
- Proof: `cd frontend && E2E_BASE_URL=http://localhost:4200 npx playwright test` runs 4 browser tests against the whole stack.

## 3. Payment by QR code (Freedom Pay, KZT)

1. Sign in as `attendee`, open **Almaty Product Conference** (KZT), click **Get tickets**, then **Proceed to payment**.
2. The **Pay for your ticket** dialog shows a QR code, the amount and "Waiting for the payment…". The backend created the payment with `pg_generate_qr=1`; the QR opens the gateway's payment page.
3. Pay "from the phone": open the payment page (scan the QR, or open the same URL in a second browser tab) and click **Pay (success)**. The first window notices the payment by itself and shows **Payment confirmed**.
4. What happened behind it: the emulator sent a signed result callback to `/api/v1/payments/callback/freedompay/`; the backend checked the MD5 signature in constant time, checked amount and currency, confirmed the payment with `get_status3` (MD5 alone is weak), and only then issued the ticket.
5. Optional: **Decline (insufficient funds)** shows the failure path; the seat hold stays until it expires.

Phone demo: set `FPAY_PUBLIC_URL=http://<laptop LAN IP>:18080`, `FPAY_EMULATOR_BIND=0.0.0.0` and a `FPAY_CONTROL_TOKEN` in `.env`, then `docker compose up -d fpay-emulator backend`. The phone and the laptop must be on the same network.

Security check to show:

```bash
docker compose exec backend python -c "
import urllib.request, urllib.parse
data = urllib.parse.urlencode({'pg_order_id': '1', 'pg_result': '1', 'pg_amount': '1', 'pg_salt': 'x', 'pg_sig': '0' * 32}).encode()
try: urllib.request.urlopen('http://localhost:8000/api/v1/payments/callback/freedompay/', data)
except urllib.error.HTTPError as e: print(e.code, e.read().decode())"
```

A forged callback gets `400` and a signed `error` reply; nothing changes in the database.

## 4. API and PostgreSQL roles

- API: OpenAPI contract in `backend/openapi.yaml`, Swagger UI at `/api/v1/docs/`; CI fails on schema drift and on breaking changes (`api-changes` check).
- Roles (`docs/DATABASE_ROLES.md`): owner (migrations), `eventhub_app` (data only, no DDL), `eventhub_readonly` (SELECT only, no password hashes or tokens).

```bash
docker compose exec backend python manage.py verify_db_roles        # 24 probes: allowed vs denied
export POSTGRES_READONLY_PASSWORD="$(grep '^POSTGRES_READONLY_PASSWORD=' .env | cut -d= -f2-)"
docker compose exec -e PGPASSWORD="$POSTGRES_READONLY_PASSWORD" db psql -h db -U eventhub_readonly -d eventhub \
  -c "select count(*) from events_event" \
  -c "insert into events_category(name,description,icon,created_at) values('x','','',now())" \
  -c "select password from auth_user limit 1"
```

The second statement fails with "read-only transaction", the third with "permission denied".

- SQL checks on real data (`backend/sql/checks/`, 30 checks, run as the read-only role):

```bash
docker compose exec backend python manage.py run_sql_checks --show-rows 3
docker compose exec -e DJANGO_DB_AS_OWNER=1 backend python manage.py run_sql_checks --inject-defects   # proves every check catches its defect, then rolls back
```

Report: `docs/reports/database-checks-report.md` (findings, analytical queries, EXPLAIN and index recommendations).

## 5. Payment test reports

- Backend: `docs/reports/backend-payment-test-report.md` — 41 cases (checkout, Stripe webhook signature, Freedom Pay signature and callbacks, refunds, races, business rules). Run: `docker compose exec backend python manage.py test --noinput payments`.
- Frontend: `docs/reports/frontend-payment-test-report.md` — 61 cases (price breakdown, payment services, success/cancel pages, group booking hold, refunds, token refresh during checkout, QR dialog). Run: `cd frontend && npm test`.

## If something goes wrong

- Emulator not reachable: `docker compose ps fpay-emulator`, then `docker compose up -d fpay-emulator`. USD events still pay through mock Stripe.
- Payment shows "processing": the success page re-checks every 2 s for a minute, then offers **Check again**.
- Start over with clean data: `docker compose down -v && docker compose up -d --build --wait` (deletes the local database).
