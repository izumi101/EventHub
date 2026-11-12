# ADR 0001: Payment provider layer

- Status: accepted (2026-10-31)
- Scope: roadmap phase 1 (`PLAN.md` 1.1-1.6)

## Context

Payments are Stripe-only and spread over five modules (`payments/services.py`,
`payments/views.py`, `bookings/payments.py`, `bookings/services.py`,
`bookings/views.py`, plus `events/billing.py` for minor units). An audit of the
code found, besides the coupling itself:

1. Single tickets use a `Payment` row; group bookings keep their own `stripe_*`
   fields on `Booking`. The "late / duplicate / orphan payment -> refund" logic
   exists three times and the booking copy records no refund state.
2. The amount and currency reported by the provider are never compared with what
   we asked for.
3. Provider calls (`Session.create`, `Refund.create`) run inside DB transactions
   while row locks are held; `cancel_event` does network I/O in a loop of
   transactions and has no retry.
4. Lock order differs between paths (Payment -> Registration in the webhook,
   Registration -> Payment in checkout): deadlock risk.
5. No webhook event dedupe; a re-delivered event after a full refund triggers a
   second refund call.
6. `Payment.status` is assigned directly in five places; `failed` is never set;
   no DB-level protection against illegal transitions.
7. Refund state is only `refunded_amount` plus the *last* refund time and
   reason; there is no per-refund ledger.
8. `STRIPE_MOCK_MODE` is interleaved with real logic; production start-up
   requires Stripe keys even for a deployment that only sells in KZT.

Freedom Pay (KZT) must be added, a failing provider must not stop sales, and
every payment must be reconcilable with the provider's records.

## Decision

### 1. One `Payment` per payable thing, provider-neutral

`payments.Payment` becomes the only place that holds money state, for both
ticket registrations and group bookings.

| Field | Notes |
|---|---|
| `registration` | OneToOne, nullable, PROTECT |
| `booking` | OneToOne to `bookings.Booking`, nullable, PROTECT |
| CheckConstraint | exactly one of `registration` / `booking` is set |
| `provider` | `stripe`, `freedompay`, `mock`, `offline` (empty only while no attempt was made) |
| `provider_session_id` | checkout session / `init_payment` id. UniqueConstraint on (`provider`, `provider_session_id`) where non-empty |
| `provider_payment_id` | payment intent / `pg_payment_id`. Indexed |
| `provider_payload` | JSONField, provider-specific and **never** secrets or card data |
| `amount`, `currency` | Decimal(12, 2); currency stored upper-case ISO 4217 (existing lower-case values are migrated) |
| `status` | see state machine |
| `refunded_amount` | maintained as the sum of succeeded `Refund` rows |
| `method` | unchanged (`card`, `offline`) because the frontend renders it |
| `attempt` | integer, incremented for each new provider session on the same payment |

`stripe_payment_intent_id` / `stripe_checkout_session_id` (Payment) and
`stripe_session_id` / `stripe_payment_intent_id` (Booking) are replaced by the
fields above.

New tables:

- `payments.Refund`: one row per refund. `payment` FK, `amount`, `currency`,
  `kind` (`customer`, `organizer`, `event_cancelled`, `late_payment`,
  `duplicate`, `orphan`, `amount_mismatch`, `chargeback`), `status`
  (`pending`, `succeeded`, `failed`), `reason`, `requested_by` (nullable FK),
  `provider_refund_id`, `idempotency_key` (unique, derived from the row id and
  never from mutable balances), `error`, `attempts`, `created_at`,
  `processed_at`. Invariant: sum of `succeeded` + `pending` refunds of a payment
  never exceeds `payment.amount`.
- `payments.PaymentEvent`: log of provider callbacks. `provider`, `event_id`,
  `kind`, `payment` (nullable FK: orphans exist), `payload` (sanitised),
  `outcome`, `received_at`, `processed_at`. UniqueConstraint (`provider`,
  `event_id`): the row is inserted in the same transaction as the processing, so
  a re-delivery is a no-op and returns the acknowledgement again.

### 2. State machine

Statuses: `pending`, `completed`, `failed`, `expired`, `refunded`, `disputed`.
A partial refund keeps `completed` with `refunded_amount > 0` (the frontend
relies on this); `refunded` means fully refunded.

| From | To |
|---|---|
| pending | completed, failed, expired |
| failed | pending (new attempt), completed (late success report) |
| expired | pending (new attempt), completed (money arrived late) |
| completed | refunded, disputed |
| disputed | completed (dispute won), refunded (dispute lost or refunded) |
| refunded | - (terminal) |

Enforcement is layered:

1. `payments/state.py`: the transition table and `transition(payment, to, ...)`,
   the only code allowed to assign `Payment.status` (checked by a test that
   greps for direct assignments).
2. A PostgreSQL `BEFORE UPDATE` trigger on `payments_payment` rejects any status
   change not in the table, so a bug or a hand-written SQL cannot corrupt it.
3. CheckConstraints: `0 <= refunded_amount <= amount`; `status = 'refunded'`
   implies `refunded_amount = amount`; the registration/booking exclusivity.

### 3. Provider interface

```
class PaymentProvider(ABC):
    code: str                        # 'stripe', 'freedompay', 'mock'
    supported_currencies: frozenset[str] | None   # None = any
    def is_configured(self) -> bool
    def create_payment(self, order: PaymentOrder) -> CheckoutResult
    def handle_callback(self, request) -> CallbackResult   # verifies authenticity; raises InvalidCallback
    def callback_response(self, result: CallbackResult, outcome: str) -> HttpResponse
    def refund(self, payment, amount, *, idempotency_key, reason) -> RefundResult
    def get_status(self, payment) -> StatusResult
    def cancel_session(self, payment) -> None            # best effort, never raises
```

- `PaymentOrder`: `reference` (our payment id as a string), `amount`,
  `currency`, `description`, optional `lines` (Stripe shows one line per seat),
  customer email / phone, `expires_at`, `success_url`, `cancel_url`, `locale`.
- `CallbackResult` is normalised: `event_id` (provider event id, or a stable
  hash of the callback for providers without one), `kind` (`paid`, `failed`,
  `expired`, `refunded`, `dispute_opened`, `dispute_won`, `dispute_lost`,
  `ignored`), `reference`, `provider_session_id`, `provider_payment_id`,
  `amount`, `currency`, `raw` (sanitised).
- Money is `Decimal` in major units everywhere outside the provider module. Each
  provider owns its unit conversion (Stripe minor units incl. zero and
  three-decimal currencies move from `events/billing.py` into
  `providers/stripe.py`).
- Errors: `ProviderUnavailable` (network, 5xx, timeout: retryable and counted by
  the circuit breaker), `ProviderRejected` (4xx: not retryable),
  `InvalidCallback` (bad signature or malformed: answered 400).
- Providers are registered in `payments/providers/registry.py`; only configured
  providers are selectable. `MockProvider` replaces `STRIPE_MOCK_MODE`: it
  returns a redirect to the frontend success page and reports `paid`
  synchronously; it is refused outside DEBUG/tests exactly like the old switch.
  `STRIPE_MOCK_MODE` stays as a deprecated alias of `PAYMENTS_MOCK_MODE`.

### 4. Orchestration (`payments/service.py`)

The only module that combines providers with registrations and bookings.
Targets implement a small adapter (`RegistrationTarget`, `BookingTarget`):
`lock()`, `is_payable(now)`, `amount()`, `currency`, `description`,
`hold_deadline`, `lines()`, `confirm(payment)`.

**Rules**

- **Lock order is always Payment, then its target.** Every path, including
  checkout, mark-offline and refunds, follows it.
- **Provider network calls never happen inside a transaction that holds a row
  lock.** Checkout: (1) short transaction: lock, validate, create or reuse the
  `pending` Payment, bump `attempt`; (2) call the provider with an idempotency
  key `payment-<id>-attempt-<n>`; (3) short transaction: store the session id
  and extend the hold; on failure of (2) the payment stays pending without a
  session and the user can retry. The previous session is cancelled
  best-effort after commit.
- **Callbacks** (`process_callback(provider, request)`): authenticate, normalise,
  insert `PaymentEvent` (dedupe), then one transaction: lock the Payment found by
  (`provider`, `provider_session_id`) or by `reference`.
  - no Payment: record an orphan, enqueue a `Refund(kind=orphan)` of the received
    amount when the provider reports a payment id;
  - Payment already `completed` with a *different* provider payment id:
    `Refund(kind=duplicate)`;
  - amount or currency differs from the Payment: do not confirm, mark `failed`,
    enqueue `Refund(kind=amount_mismatch)` of the received amount, critical log;
  - target not payable any more (hold expired, cancelled): `transition` to
    `completed` (money really arrived), then `Refund(kind=late_payment)` and the
    user is notified (`payment_failed`);
  - otherwise `transition` to `completed` and `target.confirm(payment)`; this
    replaces `_confirm_paid_registration`, `confirm_booking`'s confirm branch,
    and all three "heal pending but paid" paths call it too.
- **Refunds are a ledger plus a job.** `refund_payment()` validates and inserts a
  `Refund(pending)` under the Payment lock (accounting for other pending
  refunds), then enqueues the `payments.process_refund` job in the same
  transaction (transactional outbox). The job performs the provider call outside
  any transaction using `Refund.idempotency_key`, then finalises in a short
  transaction (`succeeded` -> update `refunded_amount`, `transition` to
  `refunded` on a full refund, cancel the registration/booking on a full refund;
  `failed` after the retry budget -> alert). Interactive endpoints try the job
  inline once and answer 200 when it succeeded, 202 when it is queued and 502
  only when the provider is down; `cancel_event` just enqueues refunds, so no
  network I/O happens in its loop and a failure is retried instead of leaving a
  confirmed ticket on a cancelled event.
- `verify_payment(session_id, user)` is unified for tickets and bookings: it
  returns the Payment state and, while pending, asks `provider.get_status` and
  settles through the same code path as a callback (as an event with a
  synthetic id).

### 5. Routing and URLs

- `POST /api/v1/payments/callback/<provider>/`: one endpoint per provider.
- The legacy `/api/payments/webhook/` and `/api/v1/payments/webhook/` stay and
  route to Stripe (the address is registered at Stripe and exempt from
  deprecation headers).
- Checkout requests may carry `provider`; the default is chosen by
  `payments/routing.py` from event currency, configuration, the
  `payments.freedompay` feature flag and provider health (circuit breaker).
- Success/cancel URLs and the frontend routes `payment/success`,
  `payment/cancel` do not change.

### 6. Configuration

`PAYMENT_PROVIDERS_ENABLED` (comma list, default `stripe`) and per-provider
settings (`STRIPE_*`, `FREEDOMPAY_*`). The production start-up guard validates
the keys of every *enabled* provider and requires at least one; a KZT-only
deployment no longer needs Stripe keys.

## Migration plan (expand, migrate, contract)

1. Expand: add the new columns and tables, normalise currency case, copy
   `stripe_*` values and Booking payment fields into the new structure (a
   Payment row per paid or pending Booking), add constraints and the trigger.
   Old columns stay; old code keeps working.
2. Switch code to the new structures and providers.
3. Contract: drop the old columns in a later migration, after the code no longer
   reads them. Each migration is reversible where data allows and is tested on a
   database that contains legacy-shaped rows.

## Consequences

- Positive: one money path; Freedom Pay, Kaspi (phase 1.7) and the emulator plug
  in as providers; every refund is auditable; provider outages degrade
  gracefully; illegal state changes are impossible even from SQL.
- Cost: a sizeable migration touching payments, bookings and events; the API
  gains `202` for queued refunds and new payment statuses (`failed`,
  `expired`, `disputed`) that the frontend must map.
- Out of scope here: fiscal receipts (OFD), payouts and the ledger (phase 1B),
  Kaspi implementation (needs a contract).

## Test requirements

Every rule above has a test: callback dedupe, duplicate, orphan, late payment,
amount and currency mismatch, lock order (no deadlock under concurrent callback
and checkout), refund idempotency and retry, partial refunds, event
cancellation with a failing provider, illegal transitions rejected by the DB
trigger, migrations with legacy rows. Provider modules are tested against HTTP
level fakes (no `unittest.mock.patch` of SDK internals for the happy paths).

## Addendum: implementation notes (WP1a, expand step)

WP1a adds the new structures without switching the services; WP1b switches
them and runs the contract step.

- `payments/0004` adds the columns and tables, `payments/0005` copies the
  legacy data (rules in its docstring), `payments/0006` adds the `expired`
  and `disputed` choices. The new `Payment` columns have database defaults
  so the previous release can keep inserting rows during a deploy. Currency
  case is not normalised yet; copied booking rows use lower case like the
  existing rows. WP1b re-runs the idempotent copy before the contract step.
- `Refund` has a UUID primary key, so `idempotency_key = refund-<id>` exists
  before the insert. It also snapshots `provider` and `provider_payment_id`:
  an orphan refund (callback for an unknown payment) has no `Payment`, and a
  CheckConstraint allows a missing `payment` only for `kind = orphan` with
  both provider values set.
- The status trigger is generated from `payments/state.py:TRANSITIONS`
  (`status_trigger_sql()`) and tested inside a test transaction, but not
  installed: the legacy services still move `pending -> refunded` in one step
  (late payment). WP1b installs it with `RunSQL` together with the
  `refunded_amount` and status CheckConstraints, after the switch. The test
  that greps for direct `Payment.status` assignments also belongs to WP1b.
- The admin dashboard keeps counting group bookings from `Booking` and skips
  their ledger rows until WP1b moves it to `Payment`.
- Provider package `payments/providers/`: `base.py` (interface, frozen value
  types, errors), `registry.py`, `conf.py` (dependency-free provider table
  that `settings.py` uses for the start-up guard), `mock.py`. Additions to
  the interface: `PaymentOrder.idempotency_key` (the provider call needs it),
  `OrderLine` for `lines`, `CheckoutResult.immediate` (how the mock provider
  reports `paid` synchronously), `StatusResult.as_callback()` (a status poll
  settles through the callback path), and `PaymentRef`, the protocol a
  provider reads from a payment (a stand-in serves orphan refunds). Success
  and cancel URLs in the order carry no provider placeholders; each provider
  adds its own.
- `PAYMENT_PROVIDERS_ENABLED` (default `stripe`) and `PAYMENTS_MOCK_MODE`
  (adds `mock`; `STRIPE_MOCK_MODE` is read only while it is empty and the
  setting of that name mirrors it for the legacy services). Unknown provider
  codes are refused in every environment; with `DJANGO_DEBUG=0` every
  enabled provider must be configured, at least one real provider must be
  enabled and the mock provider is refused.
- `providers/stripe.py` uses its own `stripe.StripeClient` (API key, API
  version pinned to the one of the locked SDK, 2 network retries that reuse
  the idempotency key, 5 s connect / 30 s read timeouts) instead of setting
  `stripe.api_key` / `stripe.api_version` globally, so the legacy services
  keep their exact behaviour until WP1b; only the SDK's app info is global.
  `STRIPE_API_BASE` can point it at a fake. `checkout.session.completed`
  with `payment_status = unpaid` is `ignored` (the async events follow);
  `charge.dispute.closed` with `won`, `warning_closed` or `prevented` is
  `dispute_won`. An amount that does not fit two decimal places (a 3-decimal
  currency whose last digit is not zero) is reported as `None`, never
  rounded. `refund(amount=None)` refunds what is left.
