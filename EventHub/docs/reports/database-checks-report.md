# Database checks report: roles, demo data, integrity checks, query plans

Date: 2026-11-12. Branch `phase-1/payment-providers` (HEAD `5af93c6` plus the
uncommitted working tree, including the in-progress payments work).

Summary:

- Three PostgreSQL roles with least privilege are in place
  (`docs/DATABASE_ROLES.md`): the running app can no longer change the schema,
  reports cannot write. 24 of 24 role probes pass on an existing and on a
  fresh volume.
- `seed_demo_kz` creates realistic Almaty / Astana data in KZT: 24 events,
  4 822 registrations, 4 678 payments in 2.1 s; a second run creates nothing.
- 30 SQL checks (17 CRITICAL, 13 WARNING) return rows only when an invariant
  is broken. On the clean demo data they find **one real problem**, in
  `seed_data` (below). Each of the 30 checks catches its injected defect.
- Query plans at 305 000 payments show three missing indexes (session-id
  lookups, the event list); recommendations only, no migration added.

## 1. Environment

All runs used throwaway containers on a private network (`ehdb-*`), never the
running demo stack:

| Component | Version |
|-----------|---------|
| PostgreSQL | 16.14 (image `pgvector/pgvector:pg16`), pgvector 0.8.2 |
| Backend | image built from `EventHub/backend` with `INSTALL_SEMANTIC_SEARCH=0`: Python 3.12, Django 5.2.18, psycopg 3.3.6; code bind-mounted read-only |
| Redis | `redis:7-alpine` |
| Settings | `DJANGO_DEBUG=1`, `PAYMENTS_MOCK_MODE=1`, `DJANGO_SEED_DATA=1` (as `.env.example`) |

## 2. Data volume

Demo database after `seed_data` (runs on every start), one purchase made
through the API as a smoke test, and `seed_demo_kz`:

| Table | Rows | Notes |
|-------|-----:|-------|
| auth_user / accounts_userprofile | 609 / 609 | 600 attendees, 6 organizers (`kz_*`), 3 from `seed_data` |
| events_event | 28 | 24 KZ events + 4 from `seed_data`; 19 published, 6 completed, 1 cancelled, 1 draft, 1 pending |
| events_tickettype | 26 | Early Bird / Standard / VIP, race distances, a donation tier |
| events_seatmap / events_eventseat | 5 / 926 | 4 halls with premium / VIP / standard rows, 1 from `generate_seat_maps` |
| events_registration | 4 822 | confirmed 4 169, pending (live hold) 130, cancelled 523 |
| payments_payment | 4 678 | completed 4 015 (105 partly refunded), refunded 209, expired 205, failed 117, pending 132 |
| payments_refund | 314 | succeeded; kinds customer, organizer, event_cancelled |
| events_refundrequest | 250 | approved, pending, rejected |
| bookings_booking / bookingseat | 25 / 64 | confirmed 15, holding 2, expired 4, refunded 4 |
| events_checkinlist / checkinlog | 12 / 1 089 | 6 past events, main and VIP gates |
| events_review | 325 | 1-5 stars, from checked-in attendees |
| events_waitlistentry | 42 | waiting, offered, expired, converted |
| events_promocode / affiliate | 3 / 1 | |
| jobs_job | 0 | |

Prices are typical for the market: 3 000 ₸ (stadium, kids) to 60 000 ₸
(VIP / business passes); amounts go through `events.billing`,
`events.seat_pricing` and `bookings.payments.seat_total`, so every payment
equals what the app would charge.

## 3. Roles: verification evidence

Catalog after `setup_db_roles` on the existing volume:

```text
      rolname      | rolsuper | rolcreatedb | rolcreaterole | rolinherit | rolconnlimit | rolconfig
 eventhub_app      | f        | f           | f             | f          |           -1 |
 eventhub_readonly | f        | f           | f             | f          |           10 | {default_transaction_read_only=on,statement_timeout=60s}
 eventhub_user     | t        | t           | t             | t          |           -1 |

 table grants (schema public, 41 tables): eventhub_app SELECT 41, INSERT/UPDATE/DELETE 40 (not django_migrations);
 eventhub_readonly SELECT 34 (+ column grants on auth_user and events_webhook without password / secret)
 default ACL for eventhub_user: tables eventhub_app=arwd, eventhub_readonly=r; sequences eventhub_app=rwU; functions eventhub_app=X
 database ACL: {eventhub_user=CTc, eventhub_app=c, eventhub_readonly=c}   (PUBLIC has no CONNECT/TEMP)
```

`python manage.py verify_db_roles` (every probe rolled back):

```text
PASS  eventhub_app       SELECT events_event          expected allowed  got allowed
PASS  eventhub_app       INSERT events_category       expected allowed  got allowed
PASS  eventhub_app       UPDATE events_event          expected allowed  got allowed
PASS  eventhub_app       DELETE events_category       expected allowed  got allowed
PASS  eventhub_app       CREATE TABLE                 expected denied   got denied  (permission denied for schema public)
PASS  eventhub_app       ALTER TABLE                  expected denied   got denied  (must be owner of table events_event)
PASS  eventhub_app       DROP TABLE                   expected denied   got denied  (must be owner of table events_category)
PASS  eventhub_app       TRUNCATE                     expected denied   got denied  (permission denied for table events_category)
PASS  eventhub_app       CREATE SCHEMA                expected denied   got denied  (permission denied for database eventhub)
PASS  eventhub_app       CREATE TEMP TABLE            expected denied   got denied  (permission denied to create temporary tables in database "eventhub")
PASS  eventhub_app       write django_migrations      expected denied   got denied  (permission denied for table django_migrations)
PASS  eventhub_readonly  SELECT events_event          expected allowed  got allowed
PASS  eventhub_readonly  SELECT auth_user.username    expected allowed  got allowed
PASS  eventhub_readonly  SELECT auth_user.password    expected denied   got denied  (permission denied for table auth_user)
PASS  eventhub_readonly  SELECT django_session        expected denied   got denied  (permission denied for table django_session)
PASS  eventhub_readonly  SELECT refresh tokens        expected denied   got denied  (permission denied for table token_blacklist_outstandingtoken)
PASS  eventhub_readonly  INSERT events_category       expected denied   got denied  (permission denied for table events_category)
PASS  eventhub_readonly  UPDATE events_event          expected denied   got denied  (permission denied for table events_event)
PASS  eventhub_readonly  DELETE events_event          expected denied   got denied  (permission denied for table events_event)
PASS  eventhub_readonly  CREATE TABLE                 expected denied   got denied  (permission denied for schema public)
PASS  eventhub_app       INSERT new table (roles_probe_bcc2b7c5)  expected allowed  got allowed
PASS  eventhub_app       SELECT new table (roles_probe_bcc2b7c5)  expected allowed  got allowed
PASS  eventhub_readonly  SELECT new table (roles_probe_bcc2b7c5)  expected allowed  got allowed
PASS  eventhub_readonly  INSERT new table (roles_probe_bcc2b7c5)  expected denied   got denied  (permission denied for table roles_probe_bcc2b7c5)
All 24 role probes passed.
```

The last four lines are the ALTER DEFAULT PRIVILEGES proof: the owner created
`roles_probe_*` after the grants (as a new migration would) and the roles
could use it without another GRANT.

`psql` as the two roles:

```text
$ psql -U eventhub_readonly ...   (output condensed)
 select count(*), current_user  ->  28 | eventhub_readonly
ERROR:  cannot execute INSERT in a read-only transaction
SET                                    -- default_transaction_read_only = off
ERROR:  permission denied for table events_event      -- DELETE: the grant blocks it too
ERROR:  permission denied for table auth_user         -- SELECT password
$ psql -U eventhub_app ...
 select count(*) from events_registration  ->  4822
ERROR:  permission denied for schema public           -- CREATE TABLE
ERROR:  must be owner of table payments_payment       -- ALTER TABLE
ERROR:  permission denied for table jobs_job          -- TRUNCATE
```

Start-up scenarios (backend runs `entrypoint.sh`: `migrate`,
`setup_db_roles`, `seed_data`, gunicorn):

| Scenario | Result |
|----------|--------|
| Existing volume, old `.env` (no role variables) | `No database roles configured ... skipped.` + `WARNING: POSTGRES_APP_PASSWORD is not set ...`; `/api/health/` ok; `pg_stat_activity`: only `eventhub_user` (unchanged behaviour) |
| Same volume, restarted with role variables | `app role "eventhub_app": created`, `readonly role "eventhub_readonly": created`; health ok; backend connections: `eventhub_app`; worker (`run_worker`) connects as `eventhub_app`; `seed_data` ran as the app role. Smoke test over HTTP as attendee: login 200, event list 200, register 201 (pending), mock checkout 200, my-registrations 200 (confirmed) |
| Fresh volume with role variables | roles created on the first start, all migrations applied as owner, health ok, 24/24 probes |
| Password rotation (new `POSTGRES_APP_PASSWORD`, restart) | `updated`; health ok; the old password: `FATAL: password authentication failed for user "eventhub_app"` |

The worker container started at the same moment as a backend that had not
yet created the role failed with `password authentication failed`; in
compose the worker waits for `backend: service_healthy`, which is after
`setup_db_roles`, so this cannot happen there.

## 4. SQL checks

Files: `backend/sql/checks/NN_name.sql`, each with a header (`name`,
`severity`, `invariant`, `why`) and one query that returns rows only when the
invariant is broken. Runner: `python manage.py run_sql_checks` (as
`eventhub_readonly`, each check in its own `READ ONLY` transaction with a 60 s
timeout; exit status 1 when a CRITICAL check finds rows or a check fails to
run; `--fail-on warning|never`, `--format json`, `--show-rows N`,
`--check NAME`).

Defect proof: `run_sql_checks --inject-defects` (DEBUG only) runs every check,
injects one known defect per check (`backend/common/sql_check_defects.py`,
each builds its own rows), runs them again and rolls everything back. A
check counts as CAUGHT when it returns more rows after the injection. "After"
can be above 1 because some defects also break a neighbouring invariant (the
over-refund defect also shows up as ledger drift). The same proof runs in the
test suite (`events/test_sql_checks.py`).

| # | Check | Sev. | Clean demo data | Injected defect | Rows before → after |
|---|-------|------|----------------:|-----------------|--------------------:|
| 01 | capacity_overrun | CRIT | 0 | 2 confirmed tickets for an event with 1 spot | 0 → 1 |
| 02 | seat_held_twice | CRIT | 0 | two live registrations on one seat | 0 → 1 |
| 03 | seat_marked_free_but_taken | CRIT | 0 | sold seat left `is_available = true` | 0 → 1 |
| 04 | seat_blocked_without_holder | WARN | 0 | seat blocked, nobody holds it | 0 → 1 |
| 05 | cross_event_references | CRIT | 0 | ticket priced from another event's tier | 0 → 1 |
| 06 | confirmed_paid_ticket_without_payment | CRIT | 0 | confirmed 5 000 ₸ ticket, no payment | 0 → 2 |
| 07 | money_kept_for_void_ticket | CRIT | 0 | cancelled ticket, completed unrefunded payment | 0 → 1 |
| 08 | payment_amounts_invalid | CRIT | 0 | refunded 7 000 of a 5 000 payment | 0 → 1 |
| 09 | currency_mismatch | CRIT | 0 | USD payment for a KZT event | 0 → 1 |
| 10 | refund_ledger_over_refund | CRIT | 0 | two 3 000 refunds of a 5 000 payment | 0 → 1 |
| 11 | refund_ledger_drift | WARN | 0 | ledger refund not reflected in `refunded_amount` | 0 → 3 |
| 12 | stale_holds | WARN | **1** | hold expired an hour ago, still pending | 1 → 2 |
| 13 | checkin_on_invalid_ticket | CRIT | 0 | cancelled ticket checked in | 0 → 1 |
| 14 | checkin_outside_event_window | WARN | 0 | check-in two days before the event | 0 → 2 |
| 15 | checkin_log_wrong_event | CRIT | 0 | ticket scanned at another event's gate | 0 → 1 |
| 16 | organizer_ticket_for_own_event | CRIT | 0 | organizer registered for own event | 0 → 1 |
| 17 | tickets_held_by_non_attendees | WARN | 0 | staff account holding a ticket | 0 → 2 |
| 18 | duplicate_active_registrations | CRIT | 0 | two live tickets of one user (unique index dropped in the transaction; owner only) | 0 → 1 as owner; SKIPPED as `eventhub_app` (cannot drop the index, by design) |
| 19 | promo_over_max_uses | CRIT | 0 | `times_used` 2 of `max_uses` 1 | 0 → 1 |
| 20 | promo_counter_drift | WARN | 0 | counter 3, no registrations | 0 → 2 |
| 21 | ticket_type_oversold | CRIT | 0 | 2 tickets in a tier of 1 | 0 → 1 |
| 22 | group_booking_inconsistent | CRIT | 0 | confirmed booking without seats | 0 → 1 |
| 23 | past_event_still_published | WARN | 0 | event 3 days ago still published | 0 → 1 |
| 24 | event_data_invalid | WARN | 0 | event ends before it starts | 0 → 1 |
| 25 | orphan_money_rows | CRIT | 0 | succeeded refund of a failed payment | 0 → 1 |
| 26 | outbox_jobs_stuck | WARN | 0 | job pending for an hour | 0 → 1 |
| 27 | duplicate_provider_ids | CRIT | 0 | two payments with one Stripe session id | 0 → 1 |
| 28 | waitlist_inconsistent | WARN | 0 | offer expired an hour ago, still offered | 0 → 1 |
| 29 | review_without_attendance | WARN | 0 | 1-star review from someone without a ticket | 0 → 1 |
| 30 | refund_request_inconsistent | WARN | 0 | approved request, nothing refunded | 0 → 1 |

Result: as `eventhub_app` 29 of 30 caught, 1 skipped (needs DDL); as the owner
(`DJANGO_DB_AS_OWNER=1`) 30 of 30 caught. After both runs the demo data was
unchanged (4 822 registrations, unique index present).

Run time: all 30 checks in about 70 ms on the demo data; about 2.3 s on a
copy scaled to 305 000 payments / registrations (slowest:
`duplicate_provider_ids`, 1.3 s, four GROUP BYs over the payments table).

### Findings in the clean data

1. **`seed_data` creates a pending registration that is never released**
   (WARNING, `stale_holds`, `registration:2`). `events/management/commands/
   seed_data.py` upserts the demo attendee's "Startup Pitch Night" ticket with
   `status='pending'` and no `seat_held_until`, plus a pending payment. The
   maintenance pass only releases pending tickets whose hold has a deadline,
   so this one keeps a spot (1 of 80) forever, cannot be checked in, and is
   re-created on every container start (`DJANGO_SEED_DATA=1`). Every stack
   started from `.env.example`, including the demo stack, has it; I did not
   query the running demo database. Fix (for the owner of `seed_data`): give
   it `seat_held_until = now + SEAT_HOLD_MINUTES`, or seed it as confirmed with
   a completed payment.
2. During development `organizer_ticket_for_own_event` caught a bug in the new
   seed itself: a generated attendee name collided with organizer
   `kz_dana.abenova`, so the organizer bought tickets to her own events. Fixed
   (organizer user names are reserved before attendees are generated) and
   covered by the clean-data test.

No other check finds anything in the clean data. That is expected for data
written through the pricing and booking code, and is asserted by
`SeedDemoKzTests` (every check returns 0 rows after the seed).

Observations that are not data errors:

- Payments created by the current (legacy) checkout code have an empty
  `provider` (report 02 shows `(none)` for the smoke-test USD payment); the
  provider columns are filled by `payments/0005` / `0007` and by the new
  provider layer. Expected in the expand step of ADR 0001.
- The event list query selects `events_event.embedding` (384-dim vector) and
  the organizer's `auth_user.password` for every row because of
  `select_related` without `defer`; neither is used by the serializer.
  `.defer('embedding', 'organizer__password')` would cut row width. Not
  measured here (embeddings are empty without semantic search).

## 5. Analytical queries (`backend/sql/reports`, run as `eventhub_readonly`)

01, sales by city and event (trimmed):

```text
    city    |               event                | currency | tickets | net_revenue
 ALL CITIES | — city total —                     | KZT      |    4224 | 51474435.00
 Almaty     | — city total —                     | KZT      |    2381 | 30790285.00
 Almaty     | Almaty Jazz Festival 2026          | KZT      |     416 |  7631400.00
 Almaty     | Kazakhstan Tech Summit             | KZT      |     239 |  6371925.00
 Almaty     | Q-pop Night Live                   | KZT      |     260 |  5659000.00
 Astana     | — city total —                     | KZT      |    1843 | 20684150.00
 Astana     | Digital Steppe Forum               | KZT      |     283 |  8106000.00
 Astana     | Astana Half Marathon 2026          | KZT      |     382 |  3295700.00
 Astana     | Ballet "Swan Lake"                 | KZT      |     207 |  3233000.00
```

02, money per currency and provider:

```text
 currency | provider | payments | completed | refunded_full | refunded_partly | failed_or_expired |    gross    |  refunded  |     net     | open_pending
 KZT      | mock     |     4676 |      4014 |           209 |             105 |               322 | 55106900.00 | 3632465.00 | 51474435.00 |   1765550.00
 USD      | (none)   |        2 |         1 |             0 |               0 |                 0 |       12.00 |       0.00 |       12.00 |        15.00
```

03, occupancy (top and bottom):

```text
 title                          | status    | capacity | confirmed | on_hold | group_seats | occupancy_pct
 Q-pop Night Live               | published |      270 |       260 |       4 |           0 |          97.8
 Product Management Bootcamp    | published |       40 |        38 |       1 |           0 |          97.5
 Mozart Evening at the Philh... | completed |      128 |       105 |       0 |          10 |          89.8
 ...
 Hockey Night at Barys Arena    | published |      820 |       308 |       7 |           0 |          38.4
```

04, refund rate per category:

```text
  category  | event_cancelled | paid_tickets | refunded_full | refunded_partly | refund_rate_pct | refunded_money_pct
 Business   | f               |          156 |             6 |               5 |             7.1 |                5.3
 Music      | f               |          965 |            37 |              31 |             7.0 |                6.5
 Sports     | f               |         1665 |            51 |              41 |             5.5 |                5.0
 Education  | f               |          158 |             5 |               2 |             4.4 |                3.1
 Sports     | t               |           62 |            62 |               0 |           100.0 |              100.0
```

05, top organizers:

```text
      username       | currency | events | tickets_sold | net_revenue | avg_rating | reviews | checkin_rate_pct
 kz_dana.abenova     | KZT      |      5 |          928 | 15981600.00 |       4.14 |      28 |             89.5
 kz_nurlan.zhakupov  | KZT      |      5 |          728 | 15807925.00 |       3.94 |      18 |             83.3
 kz_yerlan.ospanov   | KZT      |      5 |         1469 | 10998000.00 |       4.21 |     205 |             84.3
```

06, checkout funnel: KZT 4 651 checkouts, 4 204 paid, 129 in progress, 201
abandoned (hold expired), 117 declined, conversion 90.4 %.

## 6. Query plans and index recommendations

`backend/sql/explain/hot_queries.sql` runs the hot API queries (captured from
the ORM with `CaptureQueriesContext` on `GET /api/v1/events/`,
`GET /api/v1/my-registrations/` and the payment / booking lookups) with
`EXPLAIN (ANALYZE, BUFFERS)`. At demo size (28 events, 4 678 payments) every
plan is under 3.2 ms, so the evidence comes from a scratch copy
(`CREATE DATABASE eventhub_scale TEMPLATE eventhub`) grown to 20 028 events,
304 822 registrations, 304 847 payments and 60 025 bookings.
`backend/sql/explain/index_experiment.sql` then creates the candidate indexes
inside a transaction, re-runs the plans and rolls back.

| Query | Today (305 k rows) | With the index (rolled back) |
|-------|--------------------|------------------------------|
| Payment by `stripe_checkout_session_id` (Stripe webhook / success page) | Parallel Seq Scan, 101 615 rows removed per worker, 6 489 buffers, **68.3 ms** | Index Scan, 4 buffers, **0.09 ms** |
| Payment by `(provider, provider_session_id)` | Index Scan on `uniq_payment_provider_session`, 0.26 ms | already indexed |
| Booking by `stripe_session_id` (group checkout webhook / success page) | Seq Scan over 60 025 rows, 1 036 buffers, **4.2 ms** | Index Scan, 4 buffers, **0.08 ms** |
| Event list, first page (`status = 'published' ORDER BY date DESC LIMIT 12`) | Seq Scan of 12 019 published events + top-N heapsort, **12.1 ms** | Index Scan, stops after 12 rows, **0.42 ms** |
| My registrations (user with 598 tickets, `ORDER BY registered_at DESC LIMIT 12`) | Bitmap Index Scan on `events_registration_user_id`, 4.7 ms | no change needed |
| Capacity subqueries of the event list | Index Scan on `events_registration.event_id` and `bookings_booking.event_id` | no change needed |

Recommendations (for a migration in the owning app; not added here because
`payments` is being changed in parallel):

1. `payments_payment (stripe_checkout_session_id) WHERE stripe_checkout_session_id <> ''`
   for as long as the legacy column is read (until the ADR 0001 contract step
   drops it). Better: move the remaining lookups to
   `(provider, provider_session_id)`, which is indexed.
2. `bookings_booking (stripe_session_id) WHERE stripe_session_id <> ''`
   (`bookings/payments.py`, `bookings/views.py`).
3. `events_event (date DESC) WHERE status = 'published'` for the public event
   list.
4. Low priority: `events_registration` has both the single-column FK index on
   `event_id` and `reg_event_status_idx (event_id, status)`; the composite one
   can serve both, so the single-column one only costs writes.
5. Unique constraints rather than plain indexes are worth considering for 1
   and 2 (check 27 guards the invariant today).

## 7. How to reproduce

In the compose stack (after setting the role variables in `.env`, see
`docs/DATABASE_ROLES.md`):

```bash
cd EventHub
docker compose exec backend python manage.py verify_db_roles
docker compose exec backend python manage.py seed_demo_kz                 # DJANGO_DEBUG=1 only
docker compose exec backend python manage.py run_sql_checks --show-rows 3
docker compose exec -e DJANGO_DB_AS_OWNER=1 backend python manage.py run_sql_checks --inject-defects
docker compose exec -T db sh -c 'PGPASSWORD=... psql -h db -U eventhub_readonly -d eventhub -f -' \
  < backend/sql/reports/01_sales_by_event_and_city.sql
docker compose exec -T db sh -c 'PGPASSWORD=... psql -h db -U eventhub_readonly -d eventhub -f -' \
  < backend/sql/explain/hot_queries.sql
```

Throwaway environment used for this report (nothing shared with the stack):

```bash
docker network create ehdb-net
docker run -d --name ehdb-db --network ehdb-net -e POSTGRES_DB=eventhub \
  -e POSTGRES_USER=eventhub_user -e POSTGRES_PASSWORD=... pgvector/pgvector:pg16
docker run -d --name ehdb-redis --network ehdb-net redis:7-alpine
docker build --build-arg INSTALL_SEMANTIC_SEARCH=0 -t ehdb-backend EventHub/backend
# backend with an env file like .env.example (POSTGRES_HOST=ehdb-db, REDIS_URL=redis://ehdb-redis:6379/0);
# first without, then with POSTGRES_APP_* / POSTGRES_READONLY_*
docker run -d --name ehdb-backend --network ehdb-net --env-file ehdb.env ehdb-backend
docker exec ehdb-backend python manage.py seed_demo_kz
docker exec ehdb-backend python manage.py run_sql_checks
# tests, like CI (owner credentials, DEBUG off):
docker run --rm --network ehdb-net -e POSTGRES_HOST=ehdb-db -e POSTGRES_USER=eventhub_user \
  -e POSTGRES_PASSWORD=... -e REDIS_URL=redis://ehdb-redis:6379/0 \
  --entrypoint python ehdb-backend manage.py test --noinput
```

Verification of the change itself: full backend suite 351 tests OK (1
skipped, 44 s) including the 22 new tests in `events/test_db_roles.py` and
`events/test_sql_checks.py`; `ruff check` and `ruff format --check` clean;
`makemigrations --check --dry-run`: no changes;
`docker compose --env-file .env.example config -q`: valid.
