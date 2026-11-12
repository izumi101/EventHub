# Payment / Frontend / Test 20 Report

Frontend automated tests of the EventHub payment flow (Angular 21, Vitest).

## 1. Scope and objective

**Objective.** Provide at least 20 meaningful, automated, passing frontend tests of the payment flow, with a written report, without changing any production code.

**In scope (existing code only):**

| Area | Production file |
|------|-----------------|
| Payment API client | `src/app/services/payment.service.ts` |
| Group booking API (checkout, verify, cancel, refund) | `src/app/services/booking.service.ts` |
| Registration refund / invoice API | `src/app/services/event.service.ts` (`requestRefund`, `refundRegistration`, `getInvoiceBlob`) |
| Money formatting | `src/app/pipes/money.pipe.ts` |
| Checkout dialog price math and validation | `src/app/components/event-detail/event-checkout-modal.component.ts` |
| Payment return pages | `payment-success/`, `payment-cancel/` components |
| Group booking hold / pay / release | `src/app/components/group-booking/group-booking.component.ts` |
| My registrations (refund request, invoice, complete payment) | `src/app/components/my-registrations/my-registrations.component.ts` |
| Token refresh during payment calls | `src/app/interceptors/auth.interceptor.ts`, `src/app/services/auth.service.ts` |

**Out of scope:** the new QR-payment component (being added in parallel), `event-detail.component.ts` (also being edited in parallel), backend, real gateway redirects, Playwright e2e (the stack is in use by another engineer).

**Environment**

| Item | Value |
|------|-------|
| Date | 2026-11-12 |
| Branch | `phase-1/payment-providers` |
| Node | v22.22.0 |
| Angular | `^21.2.25` (package.json), builder `@angular/build:unit-test` |
| Vitest | `^4.1.12` (run reports v4.1.12), DOM: jsdom `^26.1.0` |
| TypeScript | 5.9 |
| Test runner | `ng test --watch=false` (`angular.json` test target, `runner: vitest`) |

Test style: `TestBed` with `provideHttpClient` + `provideHttpClientTesting` (`HttpTestingController`) for HTTP, `useValue` mocks for services in component tests, real `ToastService` (assertions on its `toasts()` signal), `vi.useFakeTimers()` for timers, `vi.stubGlobal('location', …)` so that no test ever navigates the runner.

## 2. Test case table

Legend for the last column (all paths under `EventHub/frontend/src/app/`):

- **PAY** = `services/payment.service.spec.ts`
- **MON** = `pipes/money.pipe.spec.ts`
- **CHK** = `components/event-detail/event-checkout-modal.component.spec.ts`
- **SUC** = `components/payment-success/payment-success.component.spec.ts`
- **CAN** = `components/payment-cancel/payment-cancel.component.spec.ts`
- **GRP** = `components/group-booking/group-booking.component.spec.ts`
- **REG** = `components/my-registrations/my-registrations.component.spec.ts`
- **INT** = `interceptors/auth.interceptor.spec.ts`

"Actual result" equals "as expected" for every row except FE-PAY-61. All rows were executed in the run in section 3.

### 2.1 API clients (PAY)

| ID | Area | Scenario / inputs | Expected | Actual | Status | Automated test |
|----|------|-------------------|----------|--------|--------|----------------|
| FE-PAY-01 | PaymentService | `createCheckoutSession(42)` | `POST /api/v1/payments/create-checkout/42/`, body `{}`, returns `checkout_url` | as expected | Pass | PAY :: PaymentService > creates a checkout session with POST and an empty body, and returns the gateway URL |
| FE-PAY-02 | PaymentService | Checkout answered with 400 `{error:'Hold expired'}` | Error reaches subscriber with status 400 and body | as expected | Pass | PAY :: PaymentService > propagates a checkout failure (expired hold) with status and backend message |
| FE-PAY-03 | PaymentService | `verifyPayment('cs_test_1')` | `GET /payments/verify/` with query `session_id=cs_test_1`; status passed through | as expected | Pass | PAY :: PaymentService > verifies a payment with GET and the session id as a query parameter |
| FE-PAY-04 | PaymentService | Session id `a&b=c d` | Sent as an encoded query param, not spliced into the path (`%26`, `%20`) | as expected | Pass | PAY :: PaymentService > URL-encodes a session id instead of splicing it into the path |
| FE-PAY-05 | BookingService | `checkout('bk-1')` | `POST /bookings/bk-1/checkout/`, body `{}`, returns `checkout_url` | as expected | Pass | PAY :: BookingService (group booking payment) > starts group checkout with POST /bookings/<id>/checkout/ and returns checkout_url |
| FE-PAY-06 | BookingService | `create(7,[11,12])` answered with 409 "Seat taken" | Body `{event:7, seat_ids:[11,12]}`; 409 propagated unchanged | as expected | Pass | PAY :: BookingService (group booking payment) > holds seats with the event id and seat ids; a 409 reaches the caller unchanged |
| FE-PAY-07 | BookingService | `verify('cs_9')`, `refund('bk-1','duplicate')`, `refund('bk-2')` | Verify is GET with `session_id`; refund body `{reason}` and default `{reason:''}` | as expected | Pass | PAY :: BookingService (group booking payment) > verifies a booking payment by session id and refunds with the reason (default empty) |
| FE-PAY-08 | EventService | `requestRefund(5,'cannot attend')` | `POST /events/5/request-refund/`, body `{reason}` only | as expected | Pass | PAY :: EventService (registration refunds and invoice) > sends a refund request to the event with only the reason |
| FE-PAY-09 | EventService | Refund request answered 400 "Ticket used" | Error status 400 reaches the subscriber | as expected | Pass | PAY :: EventService (registration refunds and invoice) > propagates a refused refund request (already used ticket) as an HTTP error |
| FE-PAY-10 | EventService | Organizer `refundRegistration(9,{amount:'25.00',reason:'partial'})` | `POST /payments/refund/9/` with that body | as expected | Pass | PAY :: EventService (registration refunds and invoice) > organizer refund posts the amount and reason to the payment refund endpoint |
| FE-PAY-11 | EventService | `getInvoiceBlob(9)` | `GET /payments/invoice/9/`, `responseType` blob, no token/jwt in URL, returns the PDF blob | as expected | Pass | PAY :: EventService (registration refunds and invoice) > downloads the invoice as a blob over an authenticated GET (no token in the URL) |
| FE-PAY-12 | EventService | Invoice request answered 404 | Error status 404 reaches the subscriber | as expected | Pass | PAY :: EventService (registration refunds and invoice) > surfaces a 404 for a missing invoice to the subscriber |

### 2.2 MoneyPipe (MON)

Two pre-existing tests in the same file are not counted here.

| ID | Area | Scenario / inputs | Expected | Actual | Status | Automated test |
|----|------|-------------------|----------|--------|--------|----------------|
| FE-PAY-13 | MoneyPipe | KZT `'1234567.5'`, KZT `0` | `KZT 1,234,567.50`, `KZT 0.00` (en-US Intl uses the ISO code, no tenge sign) | as expected | Pass | MON :: MoneyPipe > shows KZT with the ISO code and thousands separators (en-US Intl has no tenge symbol) |
| FE-PAY-14 | MoneyPipe | `-5`, `0`, `'-1200.5'` USD | `-$5.00`, `$0.00`, `-$1,200.50` | as expected | Pass | MON :: MoneyPipe > formats negative and zero amounts (refund lines) without losing the sign |
| FE-PAY-15 | MoneyPipe | JPY `1234.56` | `¥1,235` (zero-decimal currency, rounded) | as expected | Pass | MON :: MoneyPipe > does not invent decimals for zero-decimal currencies (JPY) |
| FE-PAY-16 | MoneyPipe | `undefined`, `''`; value without currency / `null` currency | Empty string for no value; USD default | as expected | Pass | MON :: MoneyPipe > treats undefined and empty string as no value, and a missing currency as USD |

### 2.3 Checkout modal price math and validation (CHK)

| ID | Area | Scenario / inputs | Expected | Actual | Status | Automated test |
|----|------|-------------------|----------|--------|--------|----------------|
| FE-PAY-17 | Checkout math | Paid event, no seat/tier, GA price `80.00` | Subtotal and total `80.00` | as expected | Pass | CHK :: price breakdown > charges the dynamic GA price when no seat or tier is picked |
| FE-PAY-18 | Checkout math | Seat priced 150, then 40, then no seat price (event price 100) | Total follows the seat: 150.00, 40.00, 100.00 (recomputes on input change) | as expected | Pass | CHK :: price breakdown > prefers the selected seat price over the GA price and recomputes when the seat changes |
| FE-PAY-19 | Checkout math | Subtotal 100, tax 12%, fee 5%, fees passed to buyer | Tax 12, fee 5, total `117.00`; "Tax (12%)" and "Service fee (5%)" rendered | as expected | Pass | CHK :: price breakdown > adds tax and service fee on top when fees are passed to the buyer |
| FE-PAY-20 | Checkout math | Same rates, fees absorbed by organizer | Total `100.00`, no fee lines | as expected | Pass | CHK :: price breakdown > keeps the total at the subtotal and hides fee lines when the organizer absorbs fees |
| FE-PAY-21 | Promo | 50% promo, tax 10% passed to buyer | Subtotal 50.00, total 55.00 (tax on discounted price) | as expected | Pass | CHK :: price breakdown > applies a percent promo before tax and fees |
| FE-PAY-22 | Promo | Fixed 30 off 100; fixed 500 off 100 | 70.00; then 0.00 with tax 0 and total 0.00 (never negative) | as expected | Pass | CHK :: price breakdown > applies a fixed promo and never lets the price go below zero |
| FE-PAY-23 | Promo | Backend rejects code with 400 "Promo code expired" | Error message shown, no quote, busy flag cleared; code trimmed before the call | as expected | Pass | CHK :: price breakdown > shows the promo error from the backend and keeps no quote when the code is rejected |
| FE-PAY-24 | Promo | Seat 150 selected, 10% promo | Promo quoted with `{seat_id:5}`; subtotal 135.00 | as expected | Pass | CHK :: price breakdown > quotes the promo against the selected seat |
| FE-PAY-25 | Seat required | Seat-map event, no seat; then a seat | `canConfirm` false, "Select a seat to continue", submit toasts "Please select a seat" and emits nothing; with a seat emits `seat_id` | as expected | Pass | CHK :: validation and payload > blocks confirmation until a seat is selected on a seat-map event, then sends seat_id |
| FE-PAY-26 | Seat required | Seat map 404 | Treated as general admission; submit emits `{notes}` | as expected | Pass | CHK :: validation and payload > lets a paid event without a seat map (404) go ahead as general admission |
| FE-PAY-27 | Seat required | Seat map 500 | NOT treated as GA, confirm stays blocked, "Failed to load seat map" toast | as expected | Pass | CHK :: validation and payload > does not treat a seat-map server error as general admission |
| FE-PAY-28 | Donation minimum | Tier min 10; donation 5, then 25 | Prefilled 10; 5 rejected with error toast mentioning 10 and nothing emitted; 25 gives total 25.00 and payload `ticket_type_id`, `donation_amount: 25` | as expected | Pass | CHK :: validation and payload > rejects a donation below the tier minimum and accepts it once raised |
| FE-PAY-29 | Ticket tier | Tier with `sale_state: sold_out` | Cannot be selected; submit toasts "Please choose a ticket"; nothing emitted | as expected | Pass | CHK :: validation and payload > requires a ticket tier on a tiered event and ignores tiers that are not on sale |
| FE-PAY-30 | Ticket tier | Free tier chosen after a promo was applied | Promo dropped, total 0.00, `confirmIsPaid()` false | as expected | Pass | CHK :: validation and payload > treats a free tier as unpaid: total 0, no payment step, and drops an applied promo |
| FE-PAY-31 | Checkout validation | Required organizer question unanswered | Submit blocked with "Please answer: Company" | as expected | Pass | CHK :: validation and payload > blocks submit when a required organizer question is unanswered |
| FE-PAY-32 | Checkout payload | Promo `SAVE10` applied | Payload carries `promo_code: 'SAVE10'` | as expected | Pass | CHK :: validation and payload > sends the applied promo code in the registration payload |

### 2.4 Payment return pages (SUC, CAN)

Six pre-existing payment-success tests (completed, refunded, failed/expired, disputed, pending, booking error) are not counted here.

| ID | Area | Scenario / inputs | Expected | Actual | Status | Automated test |
|----|------|-------------------|----------|--------|--------|----------------|
| FE-PAY-33 | payment-success | Return URL `?session_id=cs_abc` | `verifyPayment` called once with `cs_abc` | as expected | Pass | SUC :: verification requests > verifies the session id taken from the return URL |
| FE-PAY-34 | payment-success | No `session_id` | "Verification failed" and "No payment session found."; gateway verification never called; no success text | as expected | Pass | SUC :: verification requests > shows an error and never calls the gateway verification when the session id is missing |
| FE-PAY-35 | payment-success | Verify returns 404 `{error:'Unknown session'}` | Backend message shown, no "Payment confirmed" | as expected | Pass | SUC :: verification requests > shows the backend message when verification is rejected, never a success view |
| FE-PAY-36 | payment-success | `?booking_id=b1&session_id=cs_2`, booking confirmed 300.00 KZT | `bookingService.verify('cs_2')` used (not `get`); "Payment confirmed", "300.00 KZT" | as expected | Pass | SUC :: verification requests > verifies a group booking by session id when Stripe returns one |
| FE-PAY-37 | payment-success | `?booking_id=b7` only (mock flow), booking status `expired` | `bookingService.get('b7')` used; "Payment refunded", not confirmed | as expected | Pass | SUC :: verification requests > reads the real booking state when there is no session (mock flow) and reports an expired hold as refunded |
| FE-PAY-38 | payment-cancel | Render | Heading "Payment cancelled", "No charges were made", no "Payment confirmed" | as expected | Pass | CAN :: PaymentCancelComponent > tells the buyer nothing was charged and does not claim a confirmed payment |
| FE-PAY-39 | payment-cancel | Render | Links to `/my-registrations` (resume the held registration) and `/` | as expected | Pass | CAN :: PaymentCancelComponent > offers a way back to the held registration and to the event list |

### 2.5 Group booking (GRP)

Fake timers, system time fixed at 2026-11-12T10:00:00Z. `window.location` is replaced by a plain object with `vi.stubGlobal`.

| ID | Area | Scenario / inputs | Expected | Actual | Status | Automated test |
|----|------|-------------------|----------|--------|--------|----------------|
| FE-PAY-40 | Group booking | Seats 10.50 and 20.25 selected | `selectionTotal` = `30.75` | as expected | Pass | GRP :: payment flow > sums the selected seat prices into the selection total |
| FE-PAY-41 | Group booking | Hold of 125 s, then +66 s | `create(7,[1,2])` called; countdown `2:05`, then `0:59` (59 s) | as expected | Pass | GRP :: payment flow > holds the selected seat ids and formats the countdown as m:ss |
| FE-PAY-42 | Group booking | Hold of 3 s runs out | Booking null, selection empty, toast "Your seat hold has expired.", seat map reloaded once; timer stopped (no second toast or reload) | as expected | Pass | GRP :: payment flow > clears the booking and selection, toasts and refreshes the seat map when the hold expires |
| FE-PAY-43 | Group booking | Component destroyed during a hold | No pending timers remain | as expected | Pass | GRP :: payment flow > stops the countdown timer when the component is destroyed |
| FE-PAY-44 | Group booking | `pay()` with checkout returning a URL | `checkout('bk-1')` called, `paying` true, `location.href` = gateway URL | as expected | Pass | GRP :: payment flow > pay() sets paying and redirects the browser to the gateway checkout_url |
| FE-PAY-45 | Group booking | `pay()` with checkout failing (500) | `paying` reset to false, toast "Payment could not be started.", no redirect | as expected | Pass | GRP :: payment flow > pay() resets paying and toasts when checkout cannot be started, without redirecting |
| FE-PAY-46 | Group booking | `pay()` without a booking | No API call, `paying` stays false | as expected | Pass | GRP :: payment flow > pay() does nothing without a held booking |
| FE-PAY-47 | Group booking | Release seats succeeds | `cancel('bk-1')` called, booking and selection cleared, "Seats released" toast, seat map reloaded, countdown stops | as expected | Pass | GRP :: payment flow > release seats cancels the booking, clears state and reloads the seat map |
| FE-PAY-48 | Group booking | Release seats fails (500) | Booking kept, toast "Could not release seats" | as expected | Pass | GRP :: payment flow > keeps the hold when releasing fails |
| FE-PAY-49 | Group booking | Hold answered 409 `{error:'Seat B1 is taken'}` | No booking, `holding` reset, backend message toasted, seat map reloaded | as expected | Pass | GRP :: payment flow > shows the backend reason and reloads the seat map when a seat is already taken |

### 2.6 My registrations (REG)

| ID | Area | Scenario / inputs | Expected | Actual | Status | Automated test |
|----|------|-------------------|----------|--------|--------|----------------|
| FE-PAY-50 | Refund request | Registration of event 5, reason "double booked" | `requestRefund(5,'double booked')`, modal closed, success toast, list reloaded (so status shows pending) | as expected | Pass | REG :: payment actions > sends the refund reason for the registration event, closes the modal and reloads |
| FE-PAY-51 | Refund request | Backend 400 "Refund already requested" | Modal stays open, `submittingRefund` false, message toasted, no reload | as expected | Pass | REG :: payment actions > keeps the modal open and shows the backend message when the refund request is refused |
| FE-PAY-52 | Refund request | Submit with no registration selected | No API call | as expected | Pass | REG :: payment actions > does not send a refund request when no registration is selected |
| FE-PAY-53 | Refund eligibility | confirmed+refundable; non-refundable; no payment; pending | Refund offered only for the first | as expected | Pass | REG :: payment actions > offers refunds only for confirmed registrations with a refundable payment |
| FE-PAY-54 | Invoice | `getInvoiceBlob` returns a Blob | Object URL created from the blob, opened in a new tab, revoked after 60 s | as expected | Pass | REG :: payment actions > opens the downloaded invoice from a blob URL and revokes it after a minute |
| FE-PAY-55 | Invoice | `getInvoiceBlob` fails (404) | Nothing opened, toast "Could not load the invoice." | as expected | Pass | REG :: payment actions > shows a toast and opens nothing when the invoice download fails |
| FE-PAY-56 | Complete payment | Pending registration, checkout returns URL | `createCheckoutSession(11)`, `payingId` 11, redirect to gateway URL | as expected | Pass | REG :: payment actions > completePayment redirects to the gateway for the registration |
| FE-PAY-57 | Complete payment | Checkout fails (hold expired) | `payingId` cleared, no redirect, toast "Could not start payment. Your seat hold may have expired.", list reloaded | as expected | Pass | REG :: payment actions > completePayment clears the busy state, toasts and reloads when the hold has expired |

### 2.7 Auth interceptor during payment (INT)

Three pre-existing interceptor tests (own-API-only token, parallel 401 shares one refresh, failed refresh logs out) are not counted here and already cover the "parallel 401s share one refresh" requirement.

| ID | Area | Scenario / inputs | Expected | Actual | Status | Automated test |
|----|------|-------------------|----------|--------|--------|----------------|
| FE-PAY-58 | Interceptor | `POST create-checkout` with expired token gets 401 | One refresh, retry is a POST with the same body and `Bearer fresh`; buyer gets `checkout_url`; no redirect to login | as expected | Pass | INT :: during a payment request > refreshes the token once and retries the checkout POST with the same body and the new token |
| FE-PAY-59 | Interceptor | `POST create-checkout` gets 409 with no refresh needed | 409 reaches caller, tokens kept, no login redirect | as expected | Pass | INT :: during a payment request > does not log out on a non-401 error such as a 409 when no refresh was needed |
| FE-PAY-60 | Interceptor | Retried request gets 401 again after a good refresh | Caller gets an error, session cleared, no second refresh (no loop) | as expected | Pass | INT :: during a payment request > gives up and logs out when the retried request is rejected with 401 again (no refresh loop) |
| FE-PAY-61 | Interceptor | 401, refresh OK, retried request gets 409 "Seat taken" | **Correct behaviour:** 409 reaches caller, user stays logged in, no navigation to `/login` | Session is wiped (`access_token` removed) and `router.navigate(['/login'])` is called | **Known defect F1** | INT :: during a payment request > F1: keeps the user logged in when the retried request fails with 409 after a successful refresh (`it.fails`, reported by Vitest as "expected fail") |

Total new cases: 61 (60 Pass, 1 Known defect). Pre-existing: 39 tests.

## 3. Execution summary

**Command** (from `EventHub/frontend`): `npm test` (runs `ng test --watch=false`).

| Metric | Before (baseline, before any change) | After |
|--------|--------------------------------------|-------|
| Test files | 9 | 14 |
| Tests | 39 passed | 99 passed + 1 expected fail = 100 |
| Failed | 0 | 0 |
| Duration | 1.96 s | 1.95 s |

New or extended spec files: 5 new (`payment.service.spec.ts`, `event-checkout-modal.component.spec.ts`, `payment-cancel.component.spec.ts`, `group-booking.component.spec.ts`, `my-registrations.component.spec.ts`) and 3 extended (`money.pipe.spec.ts`, `payment-success.component.spec.ts`, `auth.interceptor.spec.ts`).

Vitest summary, final run (trimmed):

```
 RUN  v4.1.12 /Users/ali.nd/Desktop/PROJECTS/EventHub/EventHub/frontend

 Test Files  14 passed (14)
      Tests  99 passed | 1 expected fail (100)
   Start at  19:33:54
   Duration  1.95s (transform 850ms, setup 3.00s, import 1.56s, tests 1.37s, environment 8.56s)
```

Other checks:

| Command | Result |
|---------|--------|
| `npm test` | exit 0 |
| `npm run lint` (`eslint . --max-warnings=0`) | exit 0 (an earlier run found 10 errors in the new specs, all fixed: unnecessary `??`, untyped error callback, irregular whitespace) |
| `npm run format:check` | exit 0 (`prettier --write` run only on the spec files created or changed) |

Not run, by instruction: e2e (Playwright), docker, `npm install`.

## 4. Defects and risks found

| # | Severity | Location | Finding | Evidence |
|---|----------|----------|---------|----------|
| F1 | High (known, 2026-11-11 review) | `src/app/interceptors/auth.interceptor.ts:39-48` | The retry `next(...)` sits inside the `switchMap` that is wrapped by the `catchError` meant for refresh failures. After a successful refresh, any error from the retried request (409 "seat taken", 400, 500) calls `forceLogout()` and navigates to `/login`. A buyer whose token expired mid-checkout loses the session on a business error. | FE-PAY-61 (`it.fails`). Fix: apply `catchError` to `refreshToken()` only, and retry outside it. When fixed, the test turns red: remove `.fails`. |
| N1 | Medium (new) | `event-checkout-modal.component.ts:610` and `:170` | The minimum-contribution toast hardcodes `$` (`Minimum contribution is $${min}`) and the donation input prefix is a literal `$`, although events are charged in the event currency (KZT, JPY...). A KZT buyer is told a minimum in dollars. | Code reading. FE-PAY-28 asserts only that the message contains the minimum, so it does not freeze the bug. |
| N2 | Low-Medium (new) | `event-checkout-modal.component.ts:556-578`, `:87-107` | Each displayed money line is rounded separately by `MoneyPipe` while the total is computed unrounded. Example: subtotal 1.10, tax 5%, fee 5% shows $1.10 + $0.06 + $0.06 but total $1.21 (lines add up to $1.22). Verified with `Intl.NumberFormat` in Node. Display only; the backend computes the charged amount. | Manual calculation, no test added (the single `it.fails` slot is used by F1). |
| N3 | Low (new) | `payment-success.component.ts:81-83`, `group-booking.component.ts:88,98,136,148,180` | Amounts are printed as raw `{{ amount }} {{ currency }}` ("5000.00 KZT") instead of through `MoneyPipe`, so formatting is inconsistent with the checkout dialog (`KZT 5,000.00`). | Code reading; the payment-success spec asserts the current `5000.00 KZT` text. |
| N4 | Low (new) | `payment-cancel.component.ts:31-36` | The page says "you can retry", but offers no retry button and no link back to the event page, only `/my-registrations` and `/`. | FE-PAY-39 documents what exists. |
| N5 | Low (new) | `group-booking.component.ts:296-299`, `my-registrations.component.ts:683-687` | When checkout cannot be started, the backend's message is dropped and a fixed text is shown ("Payment could not be started."), so the buyer cannot tell a taken seat from an outage. | FE-PAY-45, FE-PAY-57 assert the current texts. |
| N6 | Low (new) | `group-booking.component.ts:326-328` | If `hold_expires_at` is missing, `startCountdown` returns without a timer, so the client never expires the hold and shows a stale "Seats held" panel with a "10:00" countdown. Not covered by a test. | Code reading. |
| N7 | Info | `group-booking.component.ts:294`, `my-registrations.component.ts:681` | Redirects use `window.location.href` directly. It is not injectable, so tests must stub the global `location` (done with `vi.stubGlobal`). A small `NavigationService` would make this testable without global stubs. | Test design note. |
| N8 | Info | Brief vs. reality | The brief expected KZT to show as `₸`. `Intl.NumberFormat('en-US')` produces `KZT 5,000.00`; tests assert the real output. The pipe has no ₸ handling. | FE-PAY-13. |
| N9 | Info | Brief vs. reality | The checkout dialog has no quantity input (one registration = one ticket), so "subtotal × quantity" is not testable; group bookings sum seat prices instead (FE-PAY-40). | Code reading. |

Working tree note: during the session `git status` showed `.gitignore` modified and `EventHub/.env.bak-2026-11-06` no longer listed as untracked. I did not touch either; it was not caused by these tests.

## 5. Coverage gaps and recommendations

Not covered by these tests:

1. **Real gateway redirects (e2e).** No test follows a real Stripe / Freedom Pay redirect or the webhook-to-verify round trip. Recommended: Playwright run against the emulator (`fpay-emulator`) for success, cancel and failure returns.
2. **QR payment flow.** The new component is being added today; no tests exist for it. Add specs once it lands (status polling, expiry, error states).
3. **`event-detail.component.ts` registration/payment orchestration** (the code that receives the checkout dialog payload, calls register and then `createCheckoutSession`, redirects, handles the queue). Not touched because it is being edited in parallel. This is the main remaining gap in the money path.
4. **Rendered DOM of group booking, my-registrations and checkout buttons.** Component tests call methods directly (my-registrations, group booking) and check a few strings in the checkout dialog. Template behaviour such as disabled "Pay" while `paying`, the "Proceed to payment — total" button text and the refund-status badges is not asserted.
5. **Refund request modal (`refund-request-modal.component.ts`) and organizer refund screens** (attendee list, refund request resolution), `markOfflinePaid`, `resolveRefundRequest`.
6. **Auth service refresh in isolation.** Share-one-refresh is verified through the interceptor; `AuthService.refreshToken()` error and `finalize` reset paths are not tested directly.
7. **Idempotency / double-click protection** on "Pay" and "Confirm" (the buttons are disabled by `paying`/`registering`, but this is not asserted in the DOM).
8. **Locale and currency edge cases** beyond USD, KZT, JPY (for example three-decimal currencies such as KWD) and rounding rules (N2).
9. **Known defect F1 has no fix test beyond `it.fails`.** After the fix, remove `.fails` so the test becomes a regression guard.
10. **payment-success spec is exposed to the parallel change.** Another engineer is editing `payment-success.component.ts`. The spec was written against the version read at 2026-10-31 17:29 (mtime), and all tests passed against it. If their change alters texts or injected services, re-run and adapt the new `verification requests` block in the spec (this was not needed at the time of this run).

Recommendations, in priority order: fix F1 and add a regression test; fix N1 (currency in the donation message and prefix); round tax and fee to cents before display and total (N2); route amounts through `MoneyPipe` (N3); add the missing retry/back-to-event link on the cancel page (N4); extract a navigation service (N7); add the e2e and QR specs listed above.
