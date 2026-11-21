# Organizer dashboard

## Agent Entry

- Purpose: Contract and behaviour of the organizer dashboard (`/organizer/dashboard` in the SPA) and its API.
- Read when: Changing the dashboard, its endpoints, the event clone flow or the numbers it shows.
- Skip when: Working on the per-event pages (attendees, analytics, ticket types), which have their own endpoints.
- Canonical: Yes.
- Read next: `backend/events/analytics.py` (metric definitions), `backend/events/services/lifecycle.py` (clone).

## Why it was rebuilt (2026-11-21)

The first version loaded `GET /my-events/` (first page only, 12 events) and then one
`GET /events/{id}/stats/` per event. On prod the organizer had 16 events, so the 4
nearest ones were invisible, and one failed stats call emptied the whole list.
The "Duplicate" action, the activity feed and the trend badges were placeholders
(a success toast that did nothing, items timestamped with the event's creation date,
a hard-coded "+0"). The dashboard now reads three server-side endpoints that page,
filter, sort and aggregate in the database.

## Who can use it

A user *manages* an event when `common.permissions.can_manage_event` is true: the
organizer, an `EventStaff` co-organizer, or a superuser. The dashboard endpoints list the
events the user organizes **or** co-organizes (a superuser is not shown every event here;
the moderation queue is their dashboard). Allowed callers: profile role `organizer`, a
user with at least one co-organizer `EventStaff` row, or a superuser; anyone else gets
`403`. 2FA rules are the usual ones (`MFAJWTAuthentication`).

## Metric definitions

One definition everywhere. For any event the dashboard shows exactly what
`GET /events/{id}/analytics/` shows in `kpis` (a test asserts this):

| Field | Definition |
|---|---|
| `tickets_sold` | confirmed registrations + seats of confirmed group bookings |
| `checked_in` | checked-in confirmed registrations + checked-in seats of confirmed group bookings |
| `checkin_rate_pct` | `checked_in / tickets_sold * 100`, one decimal, `0` when nothing is sold |
| `capacity` | `max_participants` |
| `sold_through_pct` | `tickets_sold / capacity * 100`, one decimal, `0` when capacity is 0; not clamped (an overbooked event shows > 100) |
| `pending` | registrations in status `pending` |
| `net_revenue` | `events.analytics.net_revenue` semantics (ticket payments and group bookings minus refunds), decimal string, in `currency` |

## Endpoints

All under `/api/v1/`, `IsAuthenticated` + the manager check above, regular DRF throttling.

### `GET organizer/dashboard/`

Totals over **all** managed events, independent of tabs, search and paging.

```json
{
  "tabs": {"upcoming": 15, "past": 0, "drafts": 0, "inactive": 0},
  "pending_approval": 1,
  "upcoming_next_7_days": 4,
  "tickets_sold": 9,
  "checked_in": 0,
  "checkin_rate_pct": 0.0,
  "revenue": [{"currency": "KZT", "net_revenue": "124000.00"}],
  "sales_last_7_days": 6,
  "sales_previous_7_days": 3
}
```

- `pending_approval`: managed events in status `pending` that can still be published (end >= now).
- `upcoming_next_7_days`: events of the `upcoming` tab whose start `date` is in `[now, now+7d)`
  (an event already in progress is not "upcoming in the next 7 days").
- `revenue`: one entry per currency with a non-zero net revenue, sorted by currency code;
  amounts in different currencies are never added together.
- `sales_*`: tickets sold (same definition as `tickets_sold`) confirmed in `[now-7d, now)`
  and `[now-14d, now-7d)`; a registration counts at `registered_at`, a group booking at its
  `created_at` with its seat count. The SPA derives the change from these two numbers; it
  never shows a made-up trend.

### `GET organizer/events/`

| Param | Values | Default |
|---|---|---|
| `tab` | `upcoming`, `past`, `drafts`, `inactive` | `upcoming` |
| `search` | case-insensitive match on title **or** location, max 100 chars | — |
| `ordering` | `date`, `-date`, `-tickets_sold`, `-checkin_rate`, `-sold_through` | the tab's default |
| `page`, `page_size` | page size 1–50 | 20 |

Every event is in exactly one tab. "End" is `end_date`, or `date` when there is no end date.

| Tab | Rule | Default ordering |
|---|---|---|
| `upcoming` | status `published` or `pending`, end >= now | `date` (soonest first) |
| `past` | status `completed`, or status `published` with end < now | `-date` |
| `drafts` | status `draft` | `-date` |
| `inactive` | status `cancelled` or `rejected`, or status `pending` with end < now (it can no longer be published) | `-date` |

An unknown `tab` or `ordering` is a `400`. The response is the standard DRF page (`count`,
`next`, `previous`, `results`); each result is the `EventListSerializer` payload plus:

```json
{
  "is_owner": true,
  "stats": {"tickets_sold": 3, "checked_in": 0, "checkin_rate_pct": 0.0, "capacity": 140,
            "sold_through_pct": 2.1, "pending": 0, "net_revenue": "45000.00", "currency": "KZT"}
}
```

The number of SQL queries does not grow with the number of events on the page (tested).

### `GET organizer/activity/`

Real events from the last 30 days on managed events, newest first.

| Param | Meaning | Default |
|---|---|---|
| `limit` | 1–50 | 20 |
| `cursor` | the `next_cursor` of the previous page (opaque; for "load more") | — |

```json
{"results": [
  {"id": "registration:812", "type": "registration", "occurred_at": "2026-11-21T09:12:03Z",
   "event_id": 13, "event_title": "Stand-up Almaty", "attendee_name": "Dias A.",
   "quantity": 1, "amount": null, "currency": null}
], "next_cursor": "eyJ0IjoiMjAyNi0xMS0yMFQxODowMTo0NC4wMDAwMDArMDA6MDAiLCJyIjoxLCJrIjoiODEwIn0"}
```

| `type` | Source | Time |
|---|---|---|
| `registration` | a confirmed registration; id `registration:<id>` | `registered_at` |
| `group_booking` | a confirmed group booking; `quantity` = seats; id `group_booking:<uuid>` | `created_at` |
| `check_in` | a checked-in confirmed registration (`check_in:registration:<id>`) or a checked-in seat of a confirmed booking (`check_in:booking_seat:<id>`) | `checked_in_at` |
| `refund` | a `payments.Refund` with status `succeeded`; `amount` and `currency` set; id `refund:<uuid>` | `processed_at` |

`attendee_name` follows the display rule of the attendee list (first and last name, else the
username); a username that looks like an email address is cut at the `@`, so no email ever
appears in the feed. For a group booking or a booking seat it is the seat's attendee name, else
the claiming user, else the booking owner. `next_cursor` is `null` when nothing older exists.

Paging is keyset-based and exact: items are totally ordered by (time, source rank, pk)
descending, with the source rank fixed as registration (1), group booking (2), registration
check-in (3), seat check-in (4), refund (5). The cursor is urlsafe base64 JSON of the last
item's (time, rank, pk); the next page holds exactly the items after it, so no item is skipped
or repeated even when many share one timestamp (a group check-in stamps every seat at once).
A malformed or tampered `cursor`, and a bad `limit`, is a `400` field error.

### Clone: `POST events/{id}/clone/`

The endpoint already existed; the dashboard now uses it. Optional body `{"title": "..."}`
(1–200 chars after trimming); the SPA sends the localized "<title> (copy)". Without it
the server keeps its " (Copy)" suffix. The copy is a `draft`. Besides what was copied before
(core fields, seat map, ticket types, questions, promo codes with reset counters) it now
also copies **check-in lists** (name, description, colour, default flag; they have no
ticket-type relation, so there is nothing to remap, and scan logs stay with the original) and
queues the copy for search indexing like a newly created event. Without `title` the default
title is cut so that it always fits the 200-char column. An invalid `title` is a `400`. Staff, affiliates, webhooks, registrations and money
are never copied. After a clone the SPA opens the edit page of the new draft.

### Delete

Unchanged on the server: an event with sales answers `409` with an explanation, which the
SPA now shows instead of a generic failure.

## Related fix

`GET /events/{id}/stats/` counted `checked_in` over every registration status while
`total_registrations` counted only confirmed ones, so the rate could pass 100%. Both now
count confirmed registrations only.
