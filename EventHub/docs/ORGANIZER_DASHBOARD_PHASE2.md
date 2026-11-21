# Organizer dashboard — phase 2 plan

## Agent Entry

- Purpose: What comes after the dashboard rebuild (`ORGANIZER_DASHBOARD.md`): which features, in which order, why, and the API contract of the next batch.
- Read when: Starting any phase-2 dashboard feature, or re-prioritising the roadmap.
- Skip when: Fixing the existing dashboard (read `ORGANIZER_DASHBOARD.md`).
- Canonical: Yes for phase-2 scope and order; each batch gets its contract here before code.
- Read next: `ORGANIZER_DASHBOARD.md`, `backend/events/dashboard.py`, `backend/events/analytics.py`, `PLAN.md` (owner's roadmap).

## Principles

- **Production-grade, no shortcuts.** Every feature has a contract, backend + SPA tests, en/ru/kk, a11y, an e2e path, and docs.
- **No misleading numbers.** We do not show a figure the data cannot back. Example: a "payouts" screen without the ledger of roadmap phase 1Б would invent fees and payout dates, so it waits for 1Б.
- **One definition per metric.** New aggregates reuse `events/dashboard.py`, and their numbers must equal the per-event analytics page (tested, as today).
- **Time zone.** Day buckets and "today" use the platform's business time zone `NOTIFICATION_TIME_ZONE` (falls back to `TIME_ZONE`; production and `.env.example` set `Asia/Almaty`), not UTC.
- **Flags for operational risk.** Live check-in, segment messaging and the iCal feed ship behind Unleash flags (`dashboard.*`, see `FEATURE_FLAGS.md`), default off until verified on prod. Read-only views ship without flags.

## Inventory: what exists, what is missing (2026-11-21)

| # | Feature | Exists today | Missing | Blocker | Size |
|---|---|---|---|---|---|
| 1 | Sales chart across events | per-event 30-day timeline in `analytics.py`; dashboard has 7-vs-7 counts only | cross-event endpoint, ranges, per-currency series, publish markers (`Event.published_at` does not exist) | — | M |
| 2 | Ticket-type breakdown | `by_ticket_type` {name, count, revenue}; `TicketType.quantity` / `sold` / `available` | quantity and remaining in the payload | — | S |
| 3 | Payouts view | gross / refunded / net per event and currency | commission, ledger, balances, payout dates | **phase 1Б** (ledger) | L+ |
| 4 | Promo effectiveness | `PromoCode.times_used`, `Registration.promo_code` | stored discount amount (only implicit in `Payment`), aggregation | — | M |
| 5 | Today / next 7 days | `upcoming_next_7_days` count; `/scan`, attendees, check-in lists routes | the events themselves, countdown, deep links | — | S |
| 6 | Live check-in | `CheckInList`, `CheckInLog` (scanned_by, created_at), scan endpoints | per-hour / per-list / per-staff aggregation (undo netted), index, refresh channel | — (WebSocket optional) | M |
| 7 | Alerts | sold-through, sales velocity, pending count | rejection reason (**not stored**), `submitted_at`, rule evaluator, dismiss state | — | M |
| 8 | Traffic sources | affiliates: clicks counter, `Registration.affiliate`, `by_affiliate` | UTM / referrer capture, consent gating | cookie consent (PLAN 3.2) | M–L |
| 9 | Funnel | payment end only (`Payment` expired / failed, `06_sales_funnel.sql`, not exposed) | view / choice events | PostHog/Matomo + consent (PLAN 8) for the top of the funnel | M (payment end) |
| 10 | Waitlist actions | FIFO waitlist, `promote_waitlist`, read-only organizer list | offer to a chosen entry, remove entry, audit; list returns empty instead of 403 for non-managers | — | S–M |
| 11 | Segment messaging | `POST events/{id}/broadcast` with all / confirmed / pending / checked_in / ticket type | no-shows, waitlist segments, recipient preview, history, rate limit; the send loop runs inside one transaction | marketing consent (PLAN 3.2) for promotional mail | M |
| 12 | Calendar + iCal | — | month view, `.ics` builder, private feed token | — | M |
| 13 | Filters + bulk | four tabs, search, sort; single clone / submit / cancel | status filter within a tab, bulk clone / submit (bulk cancel stays single: step-up + refunds per event) | — | S–M |
| 14 | Reviews / NPS | `Review` 1–5 + comment, request email after the event | organizer summary (average, distribution, recent), NPS field | — | S–M |
| 15 | Team | `EventStaff` per event, add by username in event settings | account-level team, email invitations, audit | — | M |
| 16 | Admin | admin totals, paged moderation queue | `submitted_at` / `decided_at` / reason (SLA), organizer metrics, commission (1Б), reconciliation (Freedom Pay credentials) | 1Б, provider credentials | S–L |

Bug found while surveying, fixed in batch A: the per-event analytics timeline puts every sale older than the 30-day window into the first day, and it buckets by UTC date.

## Order

| Batch | Contents | Why now |
|---|---|---|
| **A — insight** | 1 sales chart (+ timeline bug fix), 2 ticket-type breakdown, 5 today / next 7 days, 14 reviews summary | Backend data exists, no blockers, highest daily value for organizers |
| **B — moderation & alerts** | 16a event moderation history (`submitted_at`, `published_at`, `decided_at`, `decided_by`, `rejection_reason`; reject requires a reason and notifies the organizer), 7 alerts, admin SLA (oldest first, waiting time) | Rejections today give organizers no reason, and admins have no queue age. `published_at` also feeds the markers of batch A |
| **C — event day & audience** | 6 live check-in (polling first, flag), 11 segment messaging (no-shows, waitlist, preview, history, batching, flag), 10 waitlist actions | Operational features; flags because they act on real attendees |
| **D — planning tools** | 12 calendar + iCal (feed behind a flag), 13 status filter + bulk clone/submit, 4 promo effectiveness (adds a stored discount column with backfill), 15 team invitations | Useful, not urgent |
| **Later, blocked** | 3 payouts (phase 1Б ledger), 8 traffic sources and 9 full funnel (consent + PostHog/Matomo, PLAN 3.2 / 8), 16 reconciliation (Freedom Pay credentials) and commission metrics (1Б) | Need roadmap work outside the dashboard |

Batch B's migration adds `published_at`. Until it lands, batch A's markers use the field when present and otherwise draw none. They are never guessed from `updated_at`.

## Batch A — contract

All endpoints are under `/api/v1/`, with the same permission as the rest of the dashboard (`CanUseOrganizerDashboard`; managed events = organized or co-organized).

### A1. `GET organizer/sales/`

| Param | Values | Default |
|---|---|---|
| `range` | `7d`, `30d`, `90d` | `30d` |

```json
{
  "time_zone": "Asia/Almaty",
  "start": "2026-10-23",
  "end": "2026-11-21",
  "days": [{"date": "2026-11-21", "tickets": 4}],
  "revenue": [{"currency": "KZT", "days": [{"date": "2026-11-21", "net_revenue": "60000.00"}]}],
  "markers": [{"date": "2026-11-17", "event_id": 13, "title": "Stand-up Almaty", "kind": "published"}]
}
```

- **`days`:** every date in `[start, end]` is present (zero-filled), in the business time zone. A ticket counts on the day it was confirmed: a registration at `registered_at`, a group booking at `created_at` with its seat count. Same definition as `tickets_sold`.
- **`revenue`:** one series per currency (the event's currency) that had a money movement in the range, never summed across currencies. A day's revenue is payments of the day minus refunds processed that day, so the series sums to `net_revenue` over the range. "Of the day" is the day the money arrived: `Payment.paid_at` for tickets (set once, on the first move to completed, by `payments.state.mark_paid`; refunds and disputes keep it) and `Booking.confirmed_at` for group bookings (set once in `confirm_booking`). `created_at` is only the start of checkout or of the 10-minute hold: an offline payment is marked paid days later and a checkout can span midnight. A paid payment or confirmed booking that lacks the timestamp (written by the previous release after a rollback) is dated by `Coalesce(paid_at, created_at)` / `Coalesce(confirmed_at, created_at)`, never dropped. A succeeded `Refund` counts on `processed_at`, a refunded booking on `refunded_at`. Tickets (seats, registrations) stay on `registered_at` / the booking's `created_at`.
- **Migrations (expand / contract):** Release N (batch A) adds and fills the columns (`payments/0008`: column, index, backfill; `bookings/0004`: column, backfill); code writes them. Release N+1, once N is deployed and no rollback below N is possible: re-run the backfill, then add CHECK `payment_paid_at_when_paid` (and the booking equivalent). The CHECK is deliberately not in N: a code-only rollback must keep working.
- **`markers`:** events published in the range (needs batch B's `published_at`; empty until then).
- **Tests:** the SQL query count is constant in the number of events. Day boundaries are checked at 23:59 / 00:00 Almaty. The range totals equal the per-event analytics for an event whose whole life is inside the range.
- **Timeline bug fix:** `events/analytics.py` uses the same bucketing helper. Sales before the window are no longer piled onto its first day.

### A2. Ticket-type breakdown (additive change)

`GET events/{id}/analytics/` → each `by_ticket_type` row gains `quantity` (null = unlimited) and `remaining` (null = unlimited, never negative). The group-booking pseudo row keeps `quantity` / `remaining` null. On the dashboard card, an expandable "Ticket types" section reads this endpoint lazily, only when opened.

### A3. `GET organizer/today/`

Managed events that are in progress or start within the next 7 days. Ordered by start, at most 10, `published` and `pending` only.

```json
{"results": [{"id": 13, "title": "…", "date": "…", "end_date": null, "location": "…",
  "status": "published", "is_owner": true, "in_progress": false,
  "stats": {"tickets_sold": 3, "checked_in": 0, "capacity": 120}}],
 "more": 2}
```

- **SPA:** a "Today & this week" block above the list. Each event shows a countdown (client side, re-rendered every minute), and links to scan, attendees and check-in lists.
- **Empty state:** the block is not rendered when there are no such events.

### A4. `GET organizer/reviews/`

```json
{"count": 12, "average": 4.42, "distribution": {"1": 0, "2": 1, "3": 1, "4": 2, "5": 8},
 "recent": [{"event_id": 13, "event_title": "…", "rating": 5, "comment": "…", "created_at": "…", "author": "Dias A."}]}
```

- **Scope:** reviews of managed events.
- **`recent`:** the 5 latest. `author` uses the same display rule as the activity feed (never an email).
- **`average`:** null when `count` is 0.
- **SPA:** a compact rating card with the distribution bars, plus a "see all" link to the event's reviews.

### Batch A done means

Backend and SPA tests, OpenAPI regenerated, en/ru/kk, e2e extended (the sales chart renders with the right totals, the today block links work), a docs update here and in `ORGANIZER_DASHBOARD.md`, and a fresh-stack e2e run recorded in `TEST_REPORT.md`.
