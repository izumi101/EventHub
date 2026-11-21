# Cross-team test report

## Agent Entry

- Purpose: what is tested across the whole product (backend, frontend, browser, database), how to run it, the results, the bugs the testing found, and what is still not covered.
- Read when: preparing the defense, before a release, or when adding a feature that needs end-to-end coverage.
- Canonical: Yes. Older, narrower reports stay in `docs/reports/` (payments, database checks).
- Read next: `frontend/e2e/` (browser specs), `scripts/qa-db-checks.sh`, `docker-compose.qa.yml`.

Date: 2026-11-14. Code: branch `test/cross-team`, based on `integration/phase-2-4` (`ff8a2e0`: phases 1, 2 (notifications, i18n), 4.1 (2FA) and the per-domain database schemas).

## 1. Scope

Unit tests already existed for every team's work (about 560 backend and 180 frontend). What was missing was proof that the parts work **together** in a real browser against the real stack, plus one report. This round adds:

| Area | What the browser tests prove |
|---|---|
| Accounts | sign-up with the code from the real email, sign-out / sign-in, a wrong code refused, password reset by email code, password change that revokes other sessions |
| Two-factor authentication | organizer's first sign-in → enrollment with an email code → 10 recovery codes shown once → sign-in with an email code → step-up dialog ("Confirm it's you") on a protected action; authenticator-app enrollment with a computed TOTP code; sign-in with a recovery code (works once) |
| Payments | KZT ticket through the Freedom Pay QR dialog, "Pay on this device" and an emulator test card; declined card; KZT group booking paid by QR; USD ticket through mock Stripe; organizer refund of a Freedom Pay ticket behind the step-up dialog, seen by the attendee |
| Notifications | e-ticket email (HTML, inline QR, preferences link) and the bell after a purchase; an email preference that persists; event cancellation refunds and notifies every holder |
| Languages | ҚАЗ / РУС / ENG switch text, title and `<html lang>`, `Accept-Language` on API calls, kept after reload, browser language as default |
| Business rules (AGENTS.md) | seat selection persists across navigation; an organizer cannot buy their own ticket; a client cannot cancel a confirmed ticket or booking (UI **and** API) |
| Database | tables in their domain schemas, role probes, the running backend uses the app role and cannot run DDL, data invariants |

Out of scope: real Freedom Pay / Stripe accounts (none exist yet, see `HANDOFF.md`), passkeys in a browser (no WebAuthn authenticator in headless runs), load and chaos tests (roadmap phase 7).

## 2. Environment

Everything runs in Docker Compose, exactly as a developer runs it, but as an **isolated second copy** so it never touches a running development stack:

| | Developer stack | Test stack (this report) |
|---|---|---|
| Compose project | `eventhub` | `ehqa` |
| Containers | `eventhub_*` | `ehqa_*` |
| Site / API / DB / Redis / emulator | 4200 / 8000 / 5433 / 6379 / 18080 | 24200 / 28000 / 25433 / 26379 / 38080 (all on 127.0.0.1) |
| `.env` | developer's | `.env.example` with freshly generated secrets |

Services: nginx + Angular 21 SPA, Django (gunicorn + uvicorn workers), outbox worker, PostgreSQL 16 + pgvector (one schema per domain, least-privilege roles), Redis, Freedom Pay emulator. Slim backend image (`INSTALL_SEMANTIC_SEARCH=0`), `DJANGO_DEBUG=1` (console email backend, mock Stripe, demo seed data). The override `docker-compose.qa.yml` also sets `MFA_STEP_UP_MAX_AGE_SECONDS=45` (so the specs reach the step-up dialog in under a minute) and `DJANGO_THROTTLE_RATES` (one run signs in dozens of accounts from one address). Browser: Playwright 1.63, Chromium, one worker.

How the tests get what a human would get:

- **Emails** are read from the worker's log, where the console backend prints each message (`e2e/support/mail.ts` parses MIME, encoded subjects and inline parts). No test-only endpoint was added to the application.
- **TOTP codes** are computed from the secret shown on the enrollment page (`e2e/support/totp.ts`); a time step is never reused per account, because the backend rejects replays.
- **Test data**: every spec creates its own attendees (real sign-up API), organizers (created by the admin, the only way to get the role) and events, so the specs are independent and can run again on the same stack.

## 3. How to run

```bash
cd EventHub
cp .env.example /tmp/ehqa.env   # then replace every password and secret with fresh values, and set:
#   DJANGO_SEED_ADMIN_PASSWORD=<random>  DJANGO_SEED_MFA_TOTP_SECRET=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP
#   FRONTEND_URL=http://localhost:24200  DJANGO_CORS_ALLOWED_ORIGINS / DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:24200
#   FPAY_PUBLIC_URL=http://localhost:38080  POSTGRES_HOST_PORT=25433  INSTALL_SEMANTIC_SEARCH=0
COMPOSE="docker compose -p ehqa --env-file /tmp/ehqa.env -f docker-compose.yml -f docker-compose.qa.yml"
$COMPOSE up -d --build --wait

# Browser tests
cd frontend && npm ci
E2E_BASE_URL=http://localhost:24200 E2E_WORKER_CONTAINER=ehqa_worker E2E_FPAY_URL=http://localhost:38080 \
E2E_MFA_TOTP_SECRET=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP E2E_ADMIN_PASSWORD=<the admin password> \
  npx playwright test

# Database checks
cd .. && COMPOSE="$COMPOSE" scripts/qa-db-checks.sh

# Clean up (this project only)
$COMPOSE down -v
```

| Variable | Meaning |
|---|---|
| `E2E_BASE_URL` | the site under test |
| `E2E_ADMIN_PASSWORD`, `E2E_MFA_TOTP_SECRET` | the seeded admin's password and test TOTP secret (it creates organizers and approves events) |
| `E2E_WORKER_CONTAINER` | container whose log holds the emails (`eventhub_worker` by default) |
| `E2E_FPAY_URL` | the emulator as the browser sees it; its control API settles payments for set-up steps |
| `E2E_STEP_UP_MAX_AGE_SECONDS` | must match the stack's `MFA_STEP_UP_MAX_AGE_SECONDS` (45) |

Backend and frontend unit tests, as in CI:

```bash
cd backend && python manage.py test --noinput            # PostgreSQL + Redis reachable
cd frontend && npm run lint && npm run format:check && npm test && npm run build
```

CI (`.github/workflows/ci.yml`, job `e2e`) does all of this on every push: it seeds a random admin password, runs the whole Playwright suite and then `scripts/qa-db-checks.sh`.

## 4. Features × test types

Counts are test cases. Backend counts come from `manage.py test -v 2` (sum 574); frontend counts are `it(...)` blocks per spec file (178; Vitest reports 182 because of parameterised cases); browser counts are Playwright tests (23).

| Feature | Backend unit / integration | Frontend unit | Browser e2e (new) |
|---|---|---|---|
| Accounts: sign-up, sign-in, reset, change password | 20 (`accounts`) | 14 (login, auth service) | 4 (`auth.e2e.ts`) + 1 (`purchase.e2e.ts`) |
| Two-factor authentication, step-up | 118 (`mfa`) | 27 (mfa-verify, security page, step-up interceptor, auth interceptor) | 2 (`two-factor.e2e.ts`) + the step-up in 2 more specs |
| Payments: Freedom Pay, mock Stripe, refunds, ledger | 200 (`payments` without bookings) | 72 (checkout modal, QR dialog, success / cancel pages, payment and polling services, money pipe) | 4 (`payments.e2e.ts`) + 1 (`purchase.e2e.ts`) |
| Group bookings | 18 (`payments.test_freedompay_bookings`) | 14 (group-booking) | 1 (`payments.e2e.ts`) + 1 (`business-rules.e2e.ts`) |
| Seat map, holds, live updates | 7 (concurrency, WebSocket) | 6 (seat selector, SVG map) | 1 (`business-rules.e2e.ts`) + 1 WebSocket (`purchase.e2e.ts`) |
| Notifications and email | 48 (`notifications`) | 3 (preferences page) | 3 (`notifications.e2e.ts`) + e-ticket and refund emails in `payments.e2e.ts` |
| Languages (kk / ru / en) | — | 15 (language service, Accept-Language, catalog parity) + 9 (My Tickets, incl. zone label) | 2 (`i18n.e2e.ts`) |
| Critical business rules | inside `events.test_regressions` and `payments.test_regressions` (counted above) | 3 (role guard) | 3 (`business-rules.e2e.ts`) |
| Database schemas, roles, SQL checks | 39 (`test_db_schemas`, `test_db_roles`, `test_sql_checks`) | — | `scripts/qa-db-checks.sh` (4 steps) in the e2e job |
| Events, check-in, moderation, feature flags, jobs, API contract, configuration | 124 (other `events`, `featureflags`, `jobs`, `common`) | 15 (API errors, dialog, feature flags) | home page under CSP (`purchase.e2e.ts`) |

## 5. Results

All runs on 2026-11-14 against the final code of `test/cross-team`, on a fresh `ehqa` stack (`down -v`, `up --build`).

| Suite | Command | Result |
|---|---|---|
| Backend | `manage.py test --noinput` (PostgreSQL 16, Redis 7) | **574 tests, OK, 2 skipped** (56 s) |
| Backend lint | `ruff format --check . && ruff check .` | clean (207 files) |
| Frontend unit | `npm test` | **26 files, 182 tests passed** (0 expected failures: the former `it.fails` for defect F1 is now a passing regression test) |
| Frontend lint / format | `npm run lint`, `npm run format:check` | clean |
| Frontend build | `npm run build` | OK (initial bundle 816 kB raw / 199 kB transfer) |
| Browser e2e, run 1 | `npx playwright test` | **23 / 23 passed** (3.9 min), 0 flaky, 0 retries |
| Browser e2e, run 2 (same stack, idempotency) | same | **23 / 23 passed** (3.8 min): every spec creates its own data |
| Schemas | `manage.py db_schemas --check` | OK: `public` holds 0 tables; identity 17, events 20, bookings 2, payments 3, jobs 1, notifications 2, platform 4 |
| Roles | `manage.py verify_db_roles` | **82 / 82 probes passed** |
| App role, live | backend's own connection | connected as `eventhub_app`, `CREATE TABLE` denied |
| SQL data checks | `manage.py run_sql_checks` | **30 checks, 0 CRITICAL**; 1 WARNING row: `stale_holds` from the seed data (known, see section 7). Before fix 3 the same run also reported 21 `outbox_jobs_stuck` rows |

The 2 skipped backend tests (`payments.test_freedompay_emulator`) need an emulator that can call the test process back; they are skipped in CI too. The browser payment specs cover the same path through the real stack. For this report they were also run against the test stack's emulator (`FPAY_EMULATOR_URL=http://localhost:38080 FPAY_CALLBACK_HOST=host.docker.internal FPAY_SECRET=<FREEDOMPAY_SECRET_KEY> manage.py test payments.test_freedompay_emulator`): **2 / 2 passed**.

No browser test is quarantined and none needed a retry locally (CI keeps `retries: 1`).

### 5.1 Redesign regression run (2026-11-15)

After the "Concept A" redesign (`REDESIGN_PLAN.md` phases 0–5) on `integration/phase-2-4`, again on a fresh `ehqa` stack.

| Suite | Result |
|---|---|
| Backend `manage.py test --noinput` | **582 tests, OK, 5 skipped** (51 s). Run with `-e MFA_STEP_UP_MAX_AGE_SECONDS=600 -e FRONTEND_URL=http://localhost:4200`: the QA stack sets 45 s and port 24200 for the browser specs, and 12 unit tests assert the defaults (step-up window, `List-Unsubscribe` URL). Without the override those 12 fail; that is the environment, not the code |
| Frontend unit | **32 files, 265 tests passed** (adds the Discover, event card, event page, footer, shell navigation and design-token specs) |
| Frontend lint / format / build | clean; initial bundle **838 kB** raw / 207 kB transfer (budget warning at 900 kB) |
| Browser e2e, run 1 / run 2 | **23 / 23** (4.0 min) and **23 / 23** (3.8 min) |
| Browser e2e, run 3 (after the focus-ring fix, frontend rebuilt) | **23 / 23** (3.8 min) |
| DB checks (`scripts/qa-db-checks.sh`) | schemas OK, **82 / 82** role probes, app role cannot run DDL, **30 SQL checks, 0 CRITICAL**; 1 WARNING `stale_holds` row, left by the "declined card keeps the spot held" spec |

Manual matrix (dev stack, same-origin frames so every width really applies its media queries): Discover, the event page (seat-map event and free event), the checkout dialog with the seat picker, My Tickets and the QR dialog × light / dark × 1440 / 1024 / 390 px × kk / ru / en = 108 page states. Each one asserts: the theme and `<html lang>` applied, no horizontal overflow, no untranslated `key.path` text, the dialog opens and fits the width. **All passed.** (One kk run first reported "dialog not opened"; it was a second, timed-out run of the script overlapping the first. A clean rerun opened every dialog in about 200 ms.)

Also checked:

- **Keyboard:** the skip link comes first, then nav, language, search, bell, account, hero thumbnails, filter bar, rails. **Found and fixed:** the global `button { outline: none }` reset hid the focus ring on the filter chips and other buttons without their own style; there is now one `:focus-visible` ring in `@layer base`, and the filter fields draw it around the whole pill. Dialogs use `appDialog` (`role="dialog"`, `aria-modal`, focus trap, Escape, focus return).
- **Reduced motion:** a global `prefers-reduced-motion` rule shortens every animation and transition; the rails' scroll buttons switch to instant scrolling; nothing auto-plays.
- **Contrast:** `design-tokens.spec.ts` checks every text token on every surface (AA) in both themes, now including the seat-zone colours. A script also compared every visible text node with its nearest opaque background on Discover, a free event page and My Tickets, in both themes: no failures. It flagged two false positives, text over photo layers (the transparent nav over the hero, ticket titles over covers), which it cannot measure.
- **Not checked:** Safari / WebKit (no Safari in this environment; the logo uses an SVG mask and the nav is `position: sticky`, so check those on a Mac before the demo); a screen reader pass.

### 5.2 Organizer dashboard run (2026-11-21)

Branch `feat/organizer-dashboard-fixes`, fresh `ehqa` stack (`down -v`, images built from the branch).

| Suite | Result |
|---|---|
| Backend `manage.py test --noinput` (CI-like: PostgreSQL 16 + Redis) | **700 tests, OK, 2 skipped**; ruff, `makemigrations --check` and the OpenAPI diff clean |
| Frontend unit | **48 files, 482 tests passed**; lint, format and production build clean |
| Browser e2e, run 1 | 25 / 27: the new `dashboard.e2e.ts` published 22 events on the next 22 days, which pushed the demo "Online Django REST Workshop" off Discover's 12 soonest, so two `purchase.e2e.ts` specs could not find it. **Fixed in the spec**: one event stays in the next 7 days (for the "soon" callout), the rest are two years out |
| Browser e2e, run 2 | **27 / 27** (4.0 min) |
| DB checks (`scripts/qa-db-checks.sh`) | **30 SQL checks, 0 CRITICAL**; 1 WARNING `stale_holds` row from the seed data (known, section 7) |

## 6. Bugs found and fixed

Every fix is its own `fix:` commit with a regression test.

| # | Severity | Bug | Found by | Fix / regression test |
|---|---|---|---|---|
| 1 | High | `docker-compose.yml` did not pass any 2FA setting to the backend and worker. `MFA_ENCRYPTION_KEY` could not be set, so with `DJANGO_DEBUG=0` the backend refused to start; `MFA_STEP_UP_MAX_AGE_SECONDS` in `.env` (a tip in `DEMO.md`) had no effect. | the step-up specs needed a shorter step-up age | `fix(docker)`: all 7 settings of `SECURITY_2FA.md` passed through; `common/test_compose_env.py` reads the guide's table and fails when one does not reach both services |
| 2 | High (known F1) | After a successful token refresh, any error of the retried request (409 "seat taken") signed the buyer out and sent them to `/login` mid-checkout. | known since 2026-11-11, kept as `it.fails` | `fix(frontend)`: only a failed refresh or a second 401 ends the session; the `it.fails` test is a normal test now |
| 3 | Medium | In the slim image every saved event queued a search-index job that failed permanently; `run_sql_checks` then reported 21 "stuck outbox jobs" after one test run, hiding real outbox failures. | `run_sql_checks` after the first browser run | `fix(search)`: no job without sentence-transformers; `events/test_search_indexing.py` |
| 4 | Low (secret in logs) | `seed_data` printed the admin password to the backend log also when it came from `DJANGO_SEED_ADMIN_PASSWORD`. | backend log of the test stack | `fix(seed)`: only a generated password is printed; `events/test_seed_data.py` |
| 5 | Low (i18n) | My Tickets showed the seat zone code from the API (`standard`) in every language. | browser test snapshot | `fix(frontend)`: same translated label as the seat map; unit test in `my-registrations.component.spec.ts` |

Supporting change (not a bug): `DJANGO_THROTTLE_RATES` makes the rate limit of any existing scope configurable (validated: unknown scope, bad rate or duplicate stops the start). The browser stack needs it; operators can tune limits without a code change.

## 7. Known gaps and risks

- **Refunded ticket disappears from My Tickets.** A fully refunded ticket becomes a cancelled registration, and `my-registrations` excludes cancelled ones, so the attendee sees the refund only under the bell and in the email. Not changed (a product decision); the refund spec asserts today's behaviour.
- **No real payment provider.** KZT runs against the emulator, other currencies against mock Stripe. The full Stripe event set, reconciliation and fiscal receipts wait for real accounts (`HANDOFF.md`).
- **Passkeys** are covered by backend and unit tests only; the headless browser has no authenticator. A Playwright virtual authenticator (CDP `WebAuthn.addVirtualAuthenticator`) is the next step.
- **Time-based waits.** Three specs wait about 45 s for the step-up proof to age; a full run takes about 4 minutes. A test-only clock would make it faster but would add a back door to the security code, so it was not done.
- **Emails are read from container logs.** The specs need `docker logs` access to the worker (true locally and in CI). Against a remote stack, point `EMAIL_BACKEND` at a capturing SMTP server (Mailpit) instead.
- **Demo data warning.** `run_sql_checks` keeps reporting one `stale_holds` row from the seed data (a pending registration without a hold deadline, known since phase 2).
- **Not covered in the browser yet:** check-in scanner, waitlist offers, refund requests by attendees, promo codes, organizer analytics and CSV export, admin moderation, emails in kk/ru (sent in the server language today), mobile layouts.

## 8. For the presentation

1. The team built four features in parallel; each had unit tests, none proved the features work together.
2. One isolated copy of the whole stack + 23 browser tests walk through every feature like a user: sign up with an emailed code, turn on 2FA, pay by QR through the gateway emulator, get the e-ticket email, switch the language, and try to break the business rules.
3. Testing found 5 bugs (one already known), including a configuration bug that would have stopped production from starting; all are fixed with regression tests.
4. Numbers: 574 backend, 182 frontend, 23 browser tests, 82 role probes, 30 SQL checks — all green, run in CI on every push.
