# Feature flags (self-hosted Unleash)

New capabilities — payment providers, payouts, the offline scanner — ship
dark behind a flag, are rolled out gradually, and can be switched off
without a deploy. Flags live in a self-hosted [Unleash](https://docs.getunleash.io/)
server; the backend evaluates them, the SPA asks the backend.

- Backend: `EventHub/backend/featureflags/` (`Flags`, `is_enabled`, `require_flag`, `override_flags`)
- Endpoint: `GET /api/v1/feature-flags/` (authenticated)
- Frontend: `src/app/services/feature-flag.service.ts` (`FeatureFlagService`)
- Infrastructure: `unleash` + `unleash-db` in `EventHub/docker-compose.yml` (profile `flags`)

## Architecture

```text
             Unleash admin UI (127.0.0.1:4242, operators only)
                        │
               ┌────────┴────────┐        ┌──────────────┐
               │ unleash (8.2.0) │────────│  unleash-db  │  own PostgreSQL
               └────────▲────────┘        └──────────────┘
      backend token     │  poll every 15 s (+ usage metrics every 60 s)
   ┌────────────────────┼──────────────────────────┐
   │ backend: one client per worker process,       │  worker container:
   │ flag state in process memory                  │  same, in run_worker
   │                                               │
   │ is_enabled(Flags.X, user) ── evaluated locally, no network
   │ GET /api/v1/feature-flags/ ── client-visible flags for request.user
   └────────────────────▲──────────────────────────┘
                        │ JWT, once after login
                  Angular SPA (FeatureFlagService)
```

- **The registry is the single source of truth.** `featureflags/registry.py`
  declares every flag: key, default, description, owner, removal date,
  and whether the SPA may see it. Code can only ask for declared flags.
- **One Unleash client per OS process**, created lazily on the first lookup —
  never at import time, so nothing is started before gunicorn forks its
  workers. A fork hook (`os.register_at_fork`) drops an inherited client
  and lock in the child, and the client records the PID that created it,
  so every process polls with its own client (the SDK's polling thread
  does not survive a fork).
- **Lookups never touch the network and never raise.** Registration and the
  first fetch run on a background thread; the SDK evaluates flags locally
  from the state its poll last fetched (kept in process memory, not the
  SDK's shared file cache). Any error inside a lookup is logged and the
  flag's default is returned.
- **Context:** `userId` (the database id — for gradual rollouts and user
  lists), `role` (`attendee`/`organizer`) and `isStaff` as custom
  properties, plus `appName` and `environment` added by the SDK. No names,
  emails or IP addresses leave the backend.
- **Server-side evaluation for the SPA.** `GET /api/v1/feature-flags/`
  returns `{"flags": {"<key>": true|false}}` for the flags marked
  `client_visible`, evaluated for the signed-in user (`Cache-Control:
  private, no-store`). The flag names are part of the OpenAPI schema, so
  the generated TypeScript types know them.

## Using a flag

Backend:

```python
from featureflags import Flags, is_enabled, require_flag

if is_enabled(Flags.PAYMENTS_FREEDOMPAY, request.user):
    ...

class OfflineScanView(APIView):
    # 404 while the flag is off for this user; auth is checked first.
    permission_classes = [IsAuthenticated, require_flag(Flags.CHECKIN_OFFLINE_SCANNER)]
```

Background jobs call `is_enabled(flag)` or `is_enabled(flag, user)` the same way.

Tests force values with `override_flags` (context manager or decorator,
like `override_settings`); Unleash is always off in `manage.py test`:

```python
from featureflags import Flags, override_flags

@override_flags({Flags.PAYMENTS_FREEDOMPAY: True})
def test_kzt_checkout_offers_freedom_pay(self): ...
```

Frontend:

```ts
private flags = inject(FeatureFlagService);
readonly offlineScanner = this.flags.flag('checkin.offline_scanner'); // Signal<boolean>
```

```html
@if (flags.isEnabled('payments.freedompay')) { <freedom-pay-option /> }
```

Flag names are typed (`FeatureFlagName` is `keyof` the generated
`FeatureFlags` schema): a misspelt or removed flag is a compile error.
Every flag is off until the backend answers and stays off if the request
fails. The flags are loaded once per signed-in user (after login, or at
start-up with a stored session) and cleared on logout; `refresh()` re-reads them.

The SPA hides UI; the backend enforces. Guard the API with `require_flag`
or `is_enabled` as well — a flag that is only checked in the browser is not
a switch.

## Adding a flag

1. **Declare it** in `featureflags/registry.py`:

   ```python
   PAYOUTS_WEEKLY = Flag(
       key='payouts.weekly',
       default=False,
       description='Weekly organizer payouts from the ledger (roadmap phase 1B).',
       owner='payments',
       remove_by=date(2027, 9, 30),
       client_visible=False,
   )
   ```

   `manage.py check` (run by every management command) refuses invalid or
   duplicate keys.
2. **If `client_visible=True`**, regenerate the contract and the types (CI
   fails on drift):

   ```bash
   cd EventHub/backend && python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
   cd EventHub/frontend && npm run api:types
   ```

3. **Use it** behind `is_enabled` / `require_flag` / `FeatureFlagService`.
4. **Create it in Unleash** with the same name (project `default`):
   *Flags → New feature flag*, type `release` for a rollout, `kill-switch`
   for an operational off-switch, `experiment` for A/B tests. Add a strategy
   per environment (e.g. *Gradual rollout* with stickiness `userId`, or a
   constraint on `role`) and enable it in that environment.
   Until it exists in Unleash, the code uses the registry default — so the
   deploy and the Unleash change can happen in either order.

To constrain on `role` or `isStaff`, define them once under
*Configure → Context fields* (they are sent as custom properties).

## Naming

`<area>.<capability>`, lower snake case: `payments.freedompay`,
`checkin.offline_scanner`, `payouts.weekly`. The area is the backend app or
domain that owns the code path. The key is the same in the registry, in
Unleash, in the API response and in TypeScript. Never reuse a key of a
removed flag.

## The safe-default rule

The default is the value the system falls back to whenever Unleash can't
answer, so it must be the value that is safe *without anyone watching*:

- **New capability** (`release`, `experiment`): `default=False`. An outage
  must never switch on something half rolled out.
- **Kill switch** for existing behaviour (`kill-switch`, `operational`):
  `default=True`. An outage must never switch off something that works.

Unleash decides only for flags it knows. A flag that exists in Unleash but
is disabled in this environment is off even if its default is `True` —
"disabled in Unleash" is an explicit decision; "unknown to Unleash" is not.

| Situation | Result |
|---|---|
| `UNLEASH_ENABLED=0` (default; tests; the default compose stack) | registry default, no client created |
| Process just started, first fetch not finished | registry default |
| Unleash unreachable, never reached since start | registry default |
| Unleash unreachable after a successful fetch | last fetched state (kept in memory) |
| Flag not created in Unleash, or archived | registry default |
| Flag exists, disabled in this environment | off |
| Flag exists and enabled | its strategies decide for the user context |
| Any error during evaluation | registry default (logged) |
| Unknown key passed by code | off (logged as an error) |
| SPA: request failed / not loaded yet / signed out | off |

## Lifecycle and cleanup

Flags are temporary. Every flag has an `owner` and a `remove_by` date in the
registry; past that date `manage.py check` warns (`featureflags.W001`).
Unleash marks flags as *potentially stale* by type (40 days for `release`)
and shows when each flag was last evaluated (from the SDK's usage metrics).

Removing a flag, in this order:

1. Roll it out to 100 % (or off for good) in every environment; let it run.
2. Delete the losing code path, the `is_enabled`/`require_flag` checks and
   the registry entry; regenerate `openapi.yaml` and the frontend types if
   it was client-visible. Deploy.
3. Archive the flag in Unleash. (Archiving first would make old code fall
   back to the default — usually *off* — while it is still deployed.)

Long-lived operational switches (`kill-switch`) are the exception: keep
them, but still give them an owner and review the date yearly.

## Running Unleash locally

Unleash is in the opt-in compose profile `flags`; the default stack (and
CI) runs without it on the flag defaults. In `EventHub/.env`:

```bash
COMPOSE_PROFILES=flags
UNLEASH_ENABLED=1
```

```bash
cd EventHub
docker compose up -d --wait
curl -fsS http://localhost:4242/health        # {"health":"GOOD"}
```

Open <http://localhost:4242> and sign in as `admin` with
`UNLEASH_ADMIN_PASSWORD`. The backend and worker poll with
`UNLEASH_BACKEND_API_TOKEN`; a change in the UI reaches them within the
poll interval (15 s).

Scripting the local server with the dev admin token from `.env.example`:

```bash
TOKEN='*:*.dev-only-admin-token'
API=http://localhost:4242/api/admin/projects/default/features
curl -fsS -H "Authorization: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"payments.freedompay","type":"release"}' "$API"
curl -fsS -H "Authorization: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"flexibleRollout","parameters":{"rollout":"100","stickiness":"default","groupId":"payments.freedompay"}}' \
  "$API/payments.freedompay/environments/development/strategies"
curl -fsS -X POST -H "Authorization: $TOKEN" "$API/payments.freedompay/environments/development/on"
# ... and /off to switch it off again
```

From a Django shell (`docker compose exec backend python manage.py shell`):

```python
from featureflags import Flags, is_enabled
from featureflags.client import wait_until_started
is_enabled(Flags.PAYMENTS_FREEDOMPAY); wait_until_started(10)
is_enabled(Flags.PAYMENTS_FREEDOMPAY)
```

`docker compose down -v` also deletes Unleash's database (flags, users,
tokens); the next start recreates the admin user and the init tokens.

## Configuration

Backend (`settings.py`; all optional unless `UNLEASH_ENABLED=1`):

| Variable | Default | Meaning |
|---|---|---|
| `UNLEASH_ENABLED` | `0` (always off in tests) | Use Unleash; off = registry defaults |
| `UNLEASH_URL` | — (compose: `http://unleash:4242/api`) | Client API base URL |
| `UNLEASH_API_TOKEN` | — (compose: `UNLEASH_BACKEND_API_TOKEN`) | Backend token; required when enabled |
| `UNLEASH_APP_NAME` | `eventhub-backend` | Shown in Unleash *Applications* |
| `UNLEASH_ENVIRONMENT` | `development` with DEBUG, else `production` | The `environment` context field |
| `UNLEASH_REFRESH_INTERVAL` | `15` | Seconds between polls |
| `UNLEASH_METRICS_INTERVAL` | `60` | Seconds between usage-metric uploads |
| `UNLEASH_REQUEST_TIMEOUT` | `5` | Seconds per request to Unleash (background only) |

`UNLEASH_ENABLED=1` without a URL or token refuses to start
(`ImproperlyConfigured`): an explicit opt-in that can't work is a
deployment mistake, not something to degrade around silently.

Compose (`.env`):

| Variable | Required | Meaning |
|---|---|---|
| `COMPOSE_PROFILES` | — | `flags` starts `unleash` + `unleash-db` |
| `UNLEASH_DB_PASSWORD` | yes | Password of Unleash's own database |
| `UNLEASH_ADMIN_PASSWORD` | yes | Password of the first `admin` user (first start only) |
| `UNLEASH_BACKEND_API_TOKEN` | yes | `<project>:<environment>.<secret>`, created on first start; the backend's token |
| `UNLEASH_ADMIN_API_TOKEN` | no | Admin token created on first start, for local scripting; empty on servers |
| `UNLEASH_PUBLIC_URL` | no | Public URL of the admin UI (links in emails) |
| `UNLEASH_HOST_PORT` | no | Host port of the admin UI on 127.0.0.1 (4242) |
| `UNLEASH_LOG_LEVEL` | no | Unleash server log level (`warn`) |

Compose interpolates every service, active profile or not, so the three
required values must be set even where Unleash isn't started (`.env.example`
has development values).

## Tokens: management and rotation

| Token | Used by | Where it lives |
|---|---|---|
| Backend token (`*:production.<secret>`) | backend + worker, to poll and send metrics | server secret `UNLEASH_BACKEND_API_TOKEN` |
| Admin password | people, for the UI | password manager; change after first login |
| Personal access token | people/automation for the admin API | the person's own, with an expiry |
| Admin token (`*:*.<secret>`) | local scripting only (deprecated by Unleash) | dev `.env` only; empty on servers |
| Frontend token | **not used** — the SPA asks the backend | — |

The environment part of the backend token selects which flag configuration
a deployment receives: production uses a `production` token, staging a
staging one. `UNLEASH_ENVIRONMENT` only labels the context.

`INIT_*_API_TOKENS` are applied **only on Unleash's first start** (while no
tokens exist); changing them later has no effect, and they are stored as
legacy (plain) tokens. Rotate the backend token without downtime:

1. Unleash UI → *Admin → API access → New API token*: type *Backend*, same
   project(s) and environment. Copy it (secure tokens are shown once).
2. Set `UNLEASH_BACKEND_API_TOKEN` to the new value in the server's secret
   store / `.env`; recreate `backend` and `worker`
   (`docker compose up -d backend worker`). Until they restart they keep
   polling with the old token.
3. Check *Applications → eventhub-backend* shows the instances polling,
   then delete the old token.

Rotate on a schedule (e.g. every 90 days), when someone with access leaves,
and immediately if a token leaks. A leaked backend token reveals flag
configuration but cannot change it; an admin token or PAT can — revoke those
first.

## When Unleash is down

- Requests are not affected: lookups are local and never wait.
- Processes that already fetched keep the last known state (in memory);
  processes started during the outage use the registry defaults.
- The SDK keeps polling and picks up the configuration on the first poll
  after Unleash is back (≤ 15 s); no restart needed.
- The failure is logged by the `UnleashClient` logger, de-duplicated to one
  message per 5 minutes per process (`featureflags.log_filters`).
- Usage metrics for the outage window are lost (only affects the "last
  seen" statistics in the UI).
- `/api/health/` does not depend on Unleash, on purpose: a flag outage must
  not take the API out of the load balancer.

## Operations notes

- The admin UI is published on `127.0.0.1` only; reach it on a server
  through an SSH tunnel (`ssh -L 4242:127.0.0.1:4242 server`) or put it
  behind the company SSO/VPN — never on the public internet.
- Back up `unleash-db` like any other database (flags, strategies, users,
  tokens, audit log); a restore brings back the exact configuration.
- The image is pinned by tag and digest (`unleashorg/unleash-server:8.2.0@sha256:…`);
  upgrade deliberately and read the release notes (Unleash migrates its
  schema on start). On Kubernetes (roadmap phase 5) use the official Helm
  chart with a managed PostgreSQL database.
- Unleash's version check and telemetry are turned off.

## Decision

**Context.** The roadmap ships risky capabilities (new payment providers,
payouts, an offline scanner) to a live ticketing system with real money.
They must reach a subset of users first and be switchable off in seconds,
without a deploy. Data residency (Kazakhstan) matters.

**Decision.**

1. **Self-hosted Unleash (open source).** A mature flag server with gradual
   rollouts, constraints, environments, audit log, usage metrics and stale
   flag detection, official SDKs, Apache-2.0, runs on our own
   infrastructure (no user context leaves our network; no per-seat SaaS
   cost). Alternatives: SaaS (LaunchDarkly, Unleash Cloud) — user data and
   availability outside our control, cost; Flagsmith — comparable, smaller
   Python ecosystem; Django-only flags (django-waffle or a model) — no
   gradual rollout engine, audit or UI for operators, and flag reads would
   hit our main database.
2. **Server-side evaluation.** The backend evaluates every flag locally
   from polled state, with a per-flag default declared in code. The backend
   is the enforcement point anyway; one evaluation context and one source
   of truth for both API and UI; the same answer for a user in the API and
   in the SPA.
3. **No frontend SDK and no frontend token.** The SPA gets its flags from
   `GET /api/v1/feature-flags/`. Shipping an Unleash token to the browser
   would require exposing the Frontend API (or running Unleash Edge)
   publicly and would let anyone enumerate flag names and strategies; the
   backend endpoint reuses our authentication, shows only flags marked
   `client_visible`, and costs one request per sign-in.
4. **Compose profile, own database.** Unleash is optional in the compose
   stack (the backend degrades to defaults), so CI and the default
   developer setup don't depend on it. It gets its own PostgreSQL instance
   (same image as the app database): Unleash migrates its own schema on
   start, and isolation keeps credentials, backups/restores and upgrades
   independent of the application data.

**Consequences.** Flags need the discipline above (registry entry, owner,
removal date, safe default). Flag changes reach the backend within one poll
interval and the SPA on the next sign-in or `refresh()`; every process
polls on its own, so for up to one interval after a change two workers can
answer differently — don't use a flag where that matters within seconds. Each worker
process holds one SDK client and one background scheduler thread.
