# Backend Payment Test Report ("payment / backend / test 20")

## 1. Scope and objective

Objective: show, with automated tests that were actually executed, that the EventHub backend handles
payments correctly and securely. The report covers 41 backend payment test cases (the brief asked for at
least 20), grouped by area: checkout, webhook/callback handling, signature verification, refunds,
concurrency, the payment state machine, business rules, and configuration guards.

In scope: the legacy Stripe path (`payments/services.py`, `payments/views.py`), the provider layer
(`payments/providers/*`, ADR `docs/adr/0001-payment-provider-layer.md`), the Freedom Pay KZT path
(`payments/freedompay_flow.py`, `providers/freedompay*.py`, protocol in `docs/payments/freedompay-protocol.md`),
group-booking payment (`bookings/payments.py`), refunds and event cancellation (`events/services/*`), and the
payment state machine (`payments/state.py`).

Out of scope: frontend tests, browser E2E, load testing, and any call to the real Stripe or Freedom Pay
network (gateways are faked or emulated in the tests).

## 2. Environment

| Item | Value |
|---|---|
| Date | 2026-11-12 |
| Commit | branch `phase-1/payment-providers`; the run covered the code committed as `8b5fc7d` (Freedom Pay) and `e2ac898` (new tests) |
| Python | 3.12.16 |
| Django / DRF | 5.2.18 / 3.18.3 |
| stripe SDK | 16.0.0 |
| PostgreSQL | 16.14 (`pgvector/pgvector:pg16`, real transactions) |
| Redis | 7.4.8 (`redis:7-alpine`) |
| Runner | throwaway Docker containers `ehbt-db`, `ehbt-redis`, image `ehbt-backend` (built with `INSTALL_SEMANTIC_SEARCH=0`) on network `ehbt-net`, backend source mounted read-only |

The environment variables mirror CI (`.github/workflows/ci.yml`): `POSTGRES_HOST/PORT/DB/USER/PASSWORD`, plus
`REDIS_URL` and `POSTGRES_CONN_MAX_AGE=0`. The owner's `eventhub_*` stack and the `ehdb-*` containers were not touched.

## 3. Test cases

Status legend: Pass = the test passed in today's run. No case is a Known defect (see section 6).
"Actual" is "as expected" for every row because each automated assertion held; the column states what was observed.
Module prefix `payments.` is omitted in the reference column for brevity where the module starts with `test_`.

### 3.1 Checkout

| ID | Area | Scenario | Preconditions / inputs | Expected | Actual | Status | Automated test |
|---|---|---|---|---|---|---|---|
| BE-PAY-01 | checkout | Pay for a ticket whose seat hold has expired | Pending registration with `seat_held_until` in the past | Checkout refused (400), no session created | Refused with 400 | Pass | `payments.test_regressions.CheckoutStateTests.test_expired_hold_cannot_be_paid` |
| BE-PAY-02 | checkout | Stripe session uses the event currency and expires with the hold | Event in KZT, pending registration | Session in event currency, expiry tied to the hold | As expected | Pass | `payments.test_regressions.CheckoutStateTests.test_session_uses_event_currency_and_expires_with_the_hold` |
| BE-PAY-03 | checkout | KZT ticket opens a Freedom Pay page with a QR code | KZT event, pending ticket, fake gateway | Signed `init_payment` sent, redirect URL and QR returned, payment row stored | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_kzt_ticket_opens_a_freedom_pay_page_with_a_qr_code` |
| BE-PAY-04 | checkout / security (IDOR) | Another user's registration | Authenticated user posts checkout for someone else's registration id | 404, nothing created | 404 | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_another_users_registration_is_not_found` |

### 3.2 Signature verification (security)

| ID | Area | Scenario | Preconditions / inputs | Expected | Actual | Status | Automated test |
|---|---|---|---|---|---|---|---|
| BE-PAY-05 | signature | Freedom Pay signature matches the documented vector | Documented `init_payment` example | Computed signature equals the documented one | Equal | Pass | `payments.test_freedompay.SignatureTests.test_the_documented_init_payment_example` |
| BE-PAY-06 | signature | Tampered parameters fail verification | Valid signed document with one field changed | Verification fails | Failed as required | Pass | `payments.test_freedompay.SignatureTests.test_verification_rejects_tampering` |
| BE-PAY-07 | signature | XML with a DTD (XXE / entity expansion) is refused | Gateway XML containing a DOCTYPE | Parsing refused | Refused | Pass | `payments.test_freedompay.SignatureTests.test_xml_with_a_dtd_is_refused` |
| BE-PAY-08 | signature | Callback with a bad signature is refused at provider level | Callback parameters with a wrong `pg_sig` | `InvalidCallback` raised | Raised | Pass | `payments.test_freedompay.ProviderTests.test_callbacks_with_a_bad_signature_are_refused` |
| BE-PAY-09 | signature / state | Bad-signature callback through the HTTP endpoint | POST to `/api/payments/callback/freedompay/` with a forged signature | Refused, payment and registration unchanged | Refused, no change | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_bad_signature_is_refused_and_changes_nothing` |

### 3.3 Webhook / callback handling

| ID | Area | Scenario | Preconditions / inputs | Expected | Actual | Status | Automated test |
|---|---|---|---|---|---|---|---|
| BE-PAY-10 | webhook | Stripe webhook with a forged or missing signature, real SDK verification (no patching of `construct_event`) | HMAC signed with a different secret, malformed header, garbage, no header | 400 each time; registration and payment stay `pending` | 400 for all four, DB unchanged | Pass (new) | `payments.test_payment_report_gaps.StripeWebhookRealSignatureTests.test_a_forged_signature_is_rejected_and_changes_nothing` |
| BE-PAY-11 | webhook | Body altered after signing | Valid signature of the original body, body changed (`pi_gap` to `pi_evil`) | 400, registration stays `pending` | 400, unchanged | Pass (new) | `payments.test_payment_report_gaps.StripeWebhookRealSignatureTests.test_a_tampered_body_with_a_valid_signature_of_another_body_is_rejected` |
| BE-PAY-12 | webhook / replay | Valid signed delivery posted twice | Same signed `checkout.session.completed` twice | Both 200; ticket confirmed once; no refund; one payment row | As expected | Pass (new) | `payments.test_payment_report_gaps.StripeWebhookRealSignatureTests.test_a_validly_signed_delivery_confirms_once_even_when_replayed` |
| BE-PAY-13 | webhook / replay | Old signed delivery replayed outside the tolerance | Timestamp 600 s old; then 60 s old | 600 s rejected (tolerance); 60 s accepted | As expected | Pass | `payments.test_provider_stripe.WebhookTests.test_a_replayed_old_delivery_is_rejected` |
| BE-PAY-14 | callback | Paid Freedom Pay callback confirms the ticket after a gateway status check | Pending ticket, signed paid callback, fake gateway reports paid | Payment completed, registration confirmed | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_paid_callback_confirms_the_ticket_after_a_status_check` |
| BE-PAY-15 | callback / replay | Duplicate Freedom Pay callback | Same paid callback delivered twice | Applied once, same reply both times | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_duplicate_callback_is_applied_once_and_answered_alike` |
| BE-PAY-16 | callback / tampering | Callback whose amount differs from the order | Signed callback with a wrong amount | Not confirmed; money refunded | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_wrong_amount_is_not_confirmed_and_refunded` |
| BE-PAY-17 | callback / tampering | Callback in a different currency | Signed callback with a wrong currency | Not confirmed; money refunded | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_wrong_currency_is_not_confirmed_and_refunded` |
| BE-PAY-18 | callback / orphan | Paid callback for an unknown order | No payment row matches | Money refunded and the event logged | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_an_unknown_order_is_refunded_and_logged` |
| BE-PAY-19 | callback / duplicate | Second payment for an already paid ticket | Ticket already paid, another payment arrives | The second payment is refunded | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_second_payment_for_a_paid_ticket_is_refunded` |
| BE-PAY-20 | callback / late | Freedom Pay payment after the hold expired | Hold released, payment arrives | Ticket not confirmed; automatic refund | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_payment_after_the_hold_expired_is_refunded_automatically` |
| BE-PAY-21 | callback / late | Stripe payment for a released hold | Registration cancelled, paid webhook arrives | Refund called with the payment intent; registration stays `cancelled`; payment `refunded` | As expected | Pass | `payments.test_regressions.LatePaymentTests.test_payment_for_released_hold_is_refunded_not_confirmed` |
| BE-PAY-22 | callback / late (group) | Group-booking payment after expiry | Expired booking, paid session arrives | Payment refunded | As expected | Pass | `payments.test_regressions.LatePaymentTests.test_expired_group_booking_payment_is_refunded` |
| BE-PAY-23 | refund resilience | Late refund while the gateway is down | Gateway raises on refund | Refund kept pending and retried by the background job | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_late_refund_is_retried_by_the_job_when_the_gateway_is_down` |
| BE-PAY-24 | access control (IDOR) | Payment status endpoint is owner only | Another user requests `/status/<payment_id>/` | 404, same as a missing payment | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_the_status_endpoint_is_owner_only` |
| BE-PAY-25 | access control (IDOR) | Invoice access | Anonymous, stranger, owner, organizer, unknown id | 401, 403, 200 (HTML), 200, 404 | As expected | Pass (new) | `payments.test_payment_report_gaps.InvoiceAccessTests.test_only_the_owner_and_the_event_team_can_open_an_invoice` |

### 3.4 Refunds

| ID | Area | Scenario | Preconditions / inputs | Expected | Actual | Status | Automated test |
|---|---|---|---|---|---|---|---|
| BE-PAY-26 | refund | Refund above the paid amount | Paid 100.00, request 100.01 | 400; `refunded_amount` stays 0; payment `completed`; ticket `confirmed` | As expected | Pass (new) | `payments.test_payment_report_gaps.RefundBalanceTests.test_a_refund_above_the_paid_amount_is_refused_and_the_books_are_untouched` |
| BE-PAY-27 | refund | Partial refund, then the remaining balance | Paid 100.00: refund 30.00, try 70.01, then refund without amount | 30.00 keeps the ticket; 70.01 refused; final call refunds 70.00, payment `refunded` with `refunded_amount` 100.00, net 0.00, ticket `cancelled`; any further refund 400 | As expected | Pass (new) | `payments.test_payment_report_gaps.RefundBalanceTests.test_partial_then_remaining_refund_keeps_the_ledger_consistent` |
| BE-PAY-28 | refund | Second full refund | Full refund already done | 400; `refunded_amount` stays 100 | As expected | Pass | `payments.test_regressions.OrganizerMoneyTests.test_second_full_refund_is_refused` |
| BE-PAY-29 | refund | Organizer refund through Freedom Pay | Paid Freedom Pay ticket | Gateway refund issued, ledger updated | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_an_organizer_refund_returns_the_money_through_freedom_pay` |
| BE-PAY-30 | refund | Gateway refuses a refund | Fake gateway rejects | Books untouched | As expected | Pass | `payments.test_freedompay.FreedomPayFlowTests.test_a_refused_gateway_refund_leaves_the_books_alone` |
| BE-PAY-31 | refund / event cancel | Event cancellation with a failed refund | One refund raises while cancelling an event | Other tickets still processed; failure counted and survived | As expected | Pass | `events.test_regressions.MoneyTests.test_cancel_event_voids_free_tickets_and_survives_a_failed_refund` |

### 3.5 Concurrency and state machine

| ID | Area | Scenario | Preconditions / inputs | Expected | Actual | Status | Automated test |
|---|---|---|---|---|---|---|---|
| BE-PAY-32 | concurrency | Cancel racing a payment confirmation (real DB locks) | `TransactionTestCase`, two threads | Cancel waits for the confirmation, then refuses | As expected | Pass | `payments.test_freedompay.CancelConfirmConcurrencyTests.test_cancel_waits_for_the_confirmation_and_refuses` |
| BE-PAY-33 | concurrency | Two buyers, one last spot | Capacity 1, concurrent registrations | Exactly one succeeds | As expected | Pass | `events.test_concurrency.RegistrationConcurrencyTests.test_two_buyers_cannot_both_take_the_last_spot` |
| BE-PAY-34 | state machine | Every move outside the ADR table is rejected | All status pairs | Rejected, nothing written | As expected | Pass | `payments.test_state.TransitionFunctionTests.test_every_other_move_is_rejected_and_nothing_is_written` |
| BE-PAY-35 | state machine | Stale object cannot overwrite a concurrent change | Two copies of one payment | The stale write is refused | As expected | Pass | `payments.test_state.TransitionFunctionTests.test_a_stale_object_cannot_overwrite_a_concurrent_change` |
| BE-PAY-36 | state machine | The database trigger enforces the same table | Raw status update | Illegal transition rejected by PostgreSQL | As expected | Pass | `payments.test_state.StatusTriggerTests.test_the_trigger_enforces_the_same_table` |

### 3.6 Business rules and configuration guards

| ID | Area | Scenario | Preconditions / inputs | Expected | Actual | Status | Automated test |
|---|---|---|---|---|---|---|---|
| BE-PAY-37 | business rule | Organizer cannot buy a ticket to their own event | Organizer registers for own event | 400 | 400 | Pass | `events.tests.EventsTests.test_register_for_event_organizer_fails` |
| BE-PAY-38 | business rule | Client cannot cancel a confirmed booking directly | Confirmed registration, attendee calls cancel | 400; registration stays `confirmed` | As expected | Pass | `events.tests.EventsTests.test_cancel_confirmed_registration_rejected` |
| BE-PAY-39 | config guard | Mock payment mode refused in production | `DEBUG` off, mock mode requested | Startup refused | As expected | Pass | `payments.test_providers.StartupGuardTests.test_mock_mode_is_refused_in_production` |
| BE-PAY-40 | config guard | Mock provider does nothing outside debug | Mock provider, `DEBUG` off | Calls refused | As expected | Pass | `payments.test_providers.MockProviderTests.test_nothing_works_outside_debug` |
| BE-PAY-41 | config guard | Emulator and demo keys need the demo flag | Freedom Pay emulator URL and demo keys in production | Refused unless the demo flag is set | As expected | Pass | `payments.test_freedompay.ProductionGuardTests.test_the_emulator_and_demo_keys_need_the_demo_flag` |

## 4. Execution summary

Helper (kept outside the repo) runs the image with the entrypoint bypassed, because a first attempt through the
image's default entrypoint did not get the test-mode defaults (the settings detect tests by `sys.argv[1] == 'test'`,
`settings.py:21`) and refused to start; CI calls `manage.py` directly, and so does this run:

```
docker run --rm --network ehbt-net \
  -v <repo>/EventHub/backend:/app:ro -v /dev/null:/app/.env:ro \
  -e POSTGRES_HOST=ehbt-db -e POSTGRES_PORT=5432 -e POSTGRES_DB=eventhub \
  -e POSTGRES_USER=eventhub_user -e POSTGRES_PASSWORD=<ci value> \
  -e REDIS_URL=redis://ehbt-redis:6379/0 -e POSTGRES_CONN_MAX_AGE=0 \
  --entrypoint python ehbt-backend manage.py test --noinput [-v 2] <labels>
```

| Run | Command (labels) | Result |
|---|---|---|
| Selected cases BE-PAY-01 to 41 | `manage.py test --noinput -v 2` with the 41 test labels above | `Found 41 test(s)` ... `Ran 41 tests in 2.262s` ... `OK` |
| New gap file only | `manage.py test --noinput -v 2 payments.test_payment_report_gaps` | `Ran 5 tests in 0.094s` ... `OK` (before the invoice test was added; the file now has 6 tests and all 6 are inside the 41-test run) |
| Full backend suite | `manage.py test --noinput` | `Ran 357 tests in 38.721s` ... `OK (skipped=1)` |
| Lint and format | `uvx ruff@0.17.1 check .` / `uvx ruff@0.17.1 format --check .` (EventHub/backend) | `All checks passed!` / `148 files already formatted` |

Trimmed real output of the selected run:

```
Found 41 test(s).
...
test_only_the_owner_and_the_event_team_can_open_an_invoice (payments.test_payment_report_gaps.InvoiceAccessTests...) ... ok
test_a_forged_signature_is_rejected_and_changes_nothing (...StripeWebhookRealSignatureTests...) ... ok
test_a_validly_signed_delivery_confirms_once_even_when_replayed (...) ... ok
...
----------------------------------------------------------------------
Ran 41 tests in 2.262s

OK
```

The one skipped test in the full suite is `payments/test_freedompay_emulator.py` (`skipUnless(EMULATOR and SECRET)`): it
runs the pay, confirm and refund round trip against the real Freedom Pay emulator container and needs
`FPAY_EMULATOR_URL` and `FPAY_SECRET`. It was not run today and is not counted among the 41 cases.

## 5. Security-relevant cases

| Threat | Cases |
|---|---|
| Forged or missing webhook signature (Stripe, real SDK verification) | BE-PAY-10, BE-PAY-11 |
| Forged callback signature (Freedom Pay) and signature algorithm correctness | BE-PAY-05, 06, 08, 09 |
| XML external entity / DTD in gateway replies | BE-PAY-07 |
| Replay and duplicate deliveries | BE-PAY-12, 13, 15, 19 |
| Amount and currency tampering | BE-PAY-16, 17 (Freedom Pay only, see defect D-3 for Stripe) |
| IDOR on checkout, status endpoint and invoice | BE-PAY-04, 24, 25 |
| Orphan payments (money with no ticket) | BE-PAY-18 |
| Race between cancel and payment | BE-PAY-32 |
| Illegal status changes, including by raw SQL | BE-PAY-34, 35, 36 |
| Dev payment modes leaking into production | BE-PAY-39, 40, 41 |

## 6. Defects and risks

### 6.1 Defects found by the new tests

None. All six new tests passed, so no `expectedFailure` markers were needed.

### 6.2 Known, open, from code review 2026-11-11

These were re-checked against the code today. All five are still true. None has an automated test.

| # | Finding | Evidence | Impact |
|---|---|---|---|
| D-1 | Event cancellation refunds run synchronously in the request, and a failed refund is only logged (the attendee is told "the organizer will contact you"). There is no automatic retry. | `events/services/lifecycle.py:195-212` (loop calling `refund_payment`, `except Exception` then `logger.exception`) | A slow gateway slows the cancel request; failed refunds need manual follow-up. Existing case BE-PAY-31 proves the loop survives a failure, not that the refund is recovered. |
| D-2 | Offline "mark paid" does not expire an open Stripe checkout session. A card payment made after the cash mark is kept. | `payments/services.py:398-428` (`mark_offline_paid` never calls `_expire_session_quietly`, which is only used at `services.py:200`) | A buyer can pay twice, for example cash plus card. |
| D-3 | No amount or currency verification on the legacy Stripe webhook. | `payments/services.py:224-297` and `payments/views.py:162-176` (the session's amount and currency are never compared to the payment) | Only a trusted, signed Stripe event reaches this code, but a mismatched session would still confirm the ticket. Freedom Pay does check (BE-PAY-16, 17). |
| D-4 | The live Stripe webhook ignores `charge.refunded` and disputes. | `payments/views.py:162` handles only `checkout.session.completed` and `async_payment_succeeded` (the provider parser supports the other kinds, see `test_provider_stripe.WebhookTests.test_every_event_kind`, but the live view does not use it) | Refunds or chargebacks done in the Stripe dashboard are not reflected in the ledger. |
| D-5 | Group bookings stay on the Stripe/mock path, not on the provider layer. | `bookings/payments.py:56` (mock) and `bookings/payments.py:84` (`stripe.checkout.Session.create`) | KZT group bookings cannot use Freedom Pay. |

### 6.3 Other observations

- Running tests through the Docker image's default entrypoint (not the way CI does) fails at start-up
  unless `DJANGO_DEBUG=1` or a real secret key and Stripe and email settings are supplied (the production guard at
  `settings.py:42` and the later `ImproperlyConfigured` check). CI is unaffected. Impact: only anyone running tests
  through the image the way the compose file does.
- The new Stripe signature tests compute the HMAC with the documented Stripe scheme (`t=<ts>,v1=<hmac>`), so they
  verify the real SDK code path rather than a patched one. The older `payments/tests.py::test_stripe_webhook_completed`
  and `test_regressions.PaymentBase.webhook` still patch `construct_event`.

## 7. Coverage gaps and recommendations

1. Add tests for D-1 to D-5 once fixed: refund retry on cancel, expiry of the Stripe session on cash mark, amount and
   currency check on the legacy webhook, `charge.refunded` and dispute handling in the live view, and Freedom Pay for
   group bookings.
2. The emulator integration test (`test_freedompay_emulator`) is skipped without the emulator; run it in CI with the
   emulator container so the real gateway protocol round trip is checked, not only fakes.
3. Replace the older patched-`construct_event` helper in `payments/test_regressions.py` with a signed-payload helper
   (as in the new test file) so signature verification is exercised in every webhook test.
4. No tests exist for the invoice content (totals, tax, currency), only for its access control (BE-PAY-25).
5. Seat selection persisting across navigation is a frontend rule and is not covered by backend tests.
6. Add a load or soak test for the callback endpoint under duplicate and out-of-order delivery.
7. The business rules "organizer cannot buy" and "client cannot cancel confirmed" are asserted at API level only; add
   a service-level test so the rule holds for any caller path (for example group bookings).
