# Interactive Seat Map & Group Booking — Technical Spec

Status: implemented
Owner: EventHub platform
Last updated: 2026-06-05

---

## 1. Goals

Two features, built to production quality, fully modular (no god-files):

1. **Interactive SVG seat map** — a real venue plan (not a button grid):
   zoom & pan, zone/sector coloring, per-zone prices, hover tooltips,
   live availability over WebSocket, single- or multi-seat selection.

2. **Group booking** — one user reserves up to 8 seats at once, the seats are
   held for 10 minutes, the booker gets a **share link** so friends can claim
   individual seats, and the whole group is paid in one checkout. Every seat
   becomes its own ticket with a QR code.

Non-negotiables: no regressions to the existing single-seat flow, no seats
double-sold (DB row locks), seats auto-released on hold expiry, all state
changes broadcast in real time.

---

## 2. Architecture

### 2.1 New bounded context — `bookings` Django app

Group booking is a separate concern from the existing single-seat
`Registration`, so it lives in its own app. Clean separation, own migrations.

```
backend/bookings/
  models.py        Booking, BookingSeat
  serializers.py   read + write serializers
  services.py      all business logic (create/claim/confirm/release)
  views.py         thin DRF views, delegate to services
  urls.py          /api/bookings/...
  payments.py      Stripe / mock checkout for a whole booking
  apps.py
```

Reused from `events`:
- `EventSeat` (the physical seat, `is_available` flag)
- `broadcast_seat_update()` (WebSocket fan-out)
- `seat_pricing.seat_price()` (zone → price)

### 2.2 Zone pricing — `events/seat_pricing.py`

Zones finally cost different amounts. `SeatMap.layout.zone_prices` holds
multipliers; fallback to defaults:

```
standard → ×1.0   vip → ×2.0   premium → ×3.0
seat_price = round(event.price × multiplier, 2)
```

### 2.3 Data model

```
Booking
  id            UUID  (pk)
  owner         FK User
  event         FK Event
  status        holding | confirmed | cancelled | expired
  share_token   UUID  (unique, used in invite link)
  hold_expires_at  datetime
  stripe_session_id  str

BookingSeat            (== one ticket)
  booking       FK Booking (related_name=seats)
  seat          OneToOne EventSeat
  price         decimal
  attendee_name str   (filled by owner or claimer)
  claimed_by    FK User (nullable)
  ticket_uuid   UUID (unique)  → QR
  is_checked_in bool, checked_in_at
```

A `BookingSeat` row existing == the seat is held by that booking. Releasing a
booking deletes its `BookingSeat` rows and flips the seats back to available.

### 2.4 Lifecycle

```
create_booking(user, event, seat_ids[])
  → lock seats (SELECT … FOR UPDATE), verify all available
  → Booking(status=holding, hold_expires_at=now+10m)
  → BookingSeat per seat, seat.is_available=False, broadcast
  → return booking + share_token

claim_seat(share_token, seat_id, name, user?)
  → set attendee_name + claimed_by on that BookingSeat

checkout(booking)                       (bookings/payments.py)
  → mock mode: confirm instantly
  → stripe: session with N line items, metadata.booking_id

confirm_booking(booking)
  → status=confirmed, clear hold, notify owner

release_expired_bookings(event?)        (lazy, called on read + create)
  → holding bookings past hold_expires_at → status=expired,
    seats freed + broadcast, BookingSeat rows deleted
```

### 2.5 Frontend

```
services/
  booking.service.ts      REST client for /api/bookings
  seat-ws.service.ts      (existing) live seat updates

components/seat-map-svg/   REUSABLE presentational component
  seat-map-svg.component.ts
    @Input  seats, maxSelection, eventPrice, zonePrices
    @Output selectionChange
    - SVG viewBox zoom (wheel + buttons) & pan (drag)
    - zone colors, legend with prices
    - hover tooltip (row/seat/zone/price)
    - live WS patch of availability

components/group-booking/  the multi-seat flow page
components/booking-claim/   /booking/:token — friends claim a seat
```

The SVG component is used by both the event checkout (maxSelection = 1) and the
group-booking page (maxSelection = 8). One renderer, two callers.

---

## 3. API

```
POST   /api/bookings/                  {event, seat_ids[]}      → booking
GET    /api/bookings/{id}/                                      → booking (owner)
GET    /api/bookings/shared/{token}/                            → booking (public, by link)
POST   /api/bookings/shared/{token}/claim/  {seat_id, name}     → claim a seat
POST   /api/bookings/{id}/checkout/                             → {checkout_url}
POST   /api/bookings/{id}/cancel/                               → release
GET    /api/events/{id}/seat-pricing/                           → zone price table
```

---

## 4. UX

- **Seat map**: pinch/wheel zoom, drag pan, "+ / − / reset" buttons, "Stage"
  marker at top, zones tinted (VIP blue, Premium purple, Standard green),
  taken seats gray & disabled, selected seats filled primary. Hover → tooltip
  with price. Mobile: same SVG, larger touch targets.
- **Group booking**: pick up to 8 seats → side panel lists them with live
  total → "Hold seats (10:00)" countdown → share link with copy button →
  "Pay for group". Friends open the link, see the held block, type their name
  on a seat to claim it.
- **Tickets**: each seat → its own QR ticket in My Tickets.

---

## 5. Correctness

- Double-sell prevented by `select_for_update()` on the seat rows inside the
  booking transaction (same guard as single-seat).
- Hold expiry is lazy (checked on every seat-map read and booking create) — no
  cron required; seats never stay locked by an abandoned cart.
- Every seat state change calls `broadcast_seat_update()` → all open maps update
  within ~50 ms.
- Mock payment mode keeps the whole flow testable locally with no Stripe key.
