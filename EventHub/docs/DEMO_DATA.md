# Demo data on the public deployment

## Agent Entry

- Purpose: How `seed_demo_kz` fills a public demo deployment (eventhubnow.tech) with realistic data, safely, and how to remove it.
- Read when: Seeding or cleaning demo data on a `DJANGO_DEBUG=0` deployment, or changing `seed_demo_kz`.
- Skip when: Local development (`DJANGO_DEBUG=1` keeps the documented `password123` behaviour).
- Canonical: Yes.
- Read next: `backend/events/management/commands/seed_demo_kz.py`, `backend/events/demo_kz_data.py` (the 60 events), `backend/events/demo_kz_remove.py`, `backend/common/demo_seed.py`, `DEPLOY.md`.

## Goal

The platform must look as if it has been running for over a year: around 760 people, 60 events in four cities, sales that rise towards each event, every payment outcome, refunds, check-ins, reviews and a moderation queue. Both the organizer dashboard and the admin pages must have real work to show.

## Safety rules

| Rule | How |
|---|---|
| Never on a real deployment by accident | `DJANGO_DEBUG=0` requires `--i-know-this-is-a-demo` (`common/demo_seed.check_allowed`); without it the command refuses |
| No shared or known password | In demo mode every created account gets its own random password (20 characters from `secrets`: upper and lower case, digit, symbol; passes `validate_password`; never `password123`), hashed with its own salt. `DJANGO_DEBUG=1` keeps `password123` for local development |
| Passwords never in logs | They are written only to `--credentials-file PATH`, one `username<TAB>password<TAB>role` line per account created in this run (organizers first, then check-in staff, then attendees). The file is created with `O_CREAT\|O_EXCL`, mode 0600, and the command refuses an existing file (no silent overwrite). Stdout and stderr show only counts and the file path. Demo mode without `--credentials-file` is refused, and so is `--credentials-file` with `DJANGO_DEBUG=1`. A run that fails before writing anything removes the empty file again |
| No email, push or job | Accounts use the non-routable domain `demo.eventhub.local`. Rows are bulk-created: the command enqueues no job and creates no notification (asserted in tests). Later, the worker's reminders and review requests still create in-app notifications for these accounts, but `notifications.service.notify` queues no email for an address on that domain, so the real SMTP account is never used |
| Real data untouched | Real users, the owner's existing events and anything not created by the command are never modified. An existing user with a `kz_` name that is not on the demo domain stops the run instead of being reused. The only rows the command adds around real data are the events it creates for `--organizer` and that user's two co-organizer roles |
| The organizer never buys | `--organizer` never appears as a ticket holder, group-booking owner or claimer, reviewer, waitlisted user, or scanner, and is never `check_in` staff (organizers cannot buy tickets to their own event). Demo accounts are never co-organizers of that user's events |
| Money flows stay safe | Demo payments carry provider `mock` and no Stripe or Freedom Pay id. Refunding one (organizer UI, approved refund request, event cancellation, group booking) is handled explicitly in `payments.services.refund_payment` / `refund_remaining_locally`: only the books change and a `Refund` ledger row (provider `mock`) is written; Stripe and Freedom Pay are never called, with the mock mode on or off (tests run it with the mode off and every gateway patched to fail) |
| Removable | `--remove` deletes exactly what the command created; `--remove --dry-run` prints the counts first (see "Removing it") |

## Content

### People (760 attendees + staff)

- Kazakh, Russian and Korean names with correct male and female surname forms.
- Cities weighted by population: Almaty, Astana, Shymkent, Karaganda, Aktobe, Atyrau, Pavlodar, Oskemen.
- Phone numbers on real Kazakh operator prefixes (700, 701, 702, 705, 707, 708, 747, 771, 775, 776, 777, 778).
- Sign-up dates over 14 months, more of them recently (a growing platform); nobody buys before signing up. Attendees favour events in their own city, and a few are much more active than the rest.
- The 6 demo organizers (`kz_*`), 14 check-in staff (`kz_staff.*`, role `check_in` on every event with gates, 2 or 3 per event), and demo co-organizers on 6 events.
- With `--organizer <username>`, the owner's account becomes co-organizer of 2 demo organizers' events, so the dashboard shows co-organized events too.

### Events (60)

The 24 earlier specs plus 36 new hand-written ones: concerts, conferences, meetups, sport and races, theatre and stand-up, children's, exhibitions, online webinars. Venues are real places in Almaty, Astana, Shymkent and Karaganda (the Shymkent and Karaganda addresses are street-level only). Mix over time, relative to the day of seeding:

| Group | Count | Status |
|---|---|---|
| Past | 25 | completed, with check-ins, reviews, refunds |
| In progress / today | 3 | published (two running now, one starting in about three hours) |
| Upcoming, next 3 months | 22 | published |
| Drafts | 3 | draft |
| Awaiting moderation | 3 | pending (the admin queue is not empty) |
| Rejected | 2 | rejected |
| Cancelled | 2 | cancelled, buyers refunded |

No past event is left `published`: the worker completes an event within a minute of its end, and the `past_event_still_published` data check reports it as a stopped worker. (The dashboard still files a published event that just ended under "past".)

Formats: seated halls with seat maps and zones, tiered tickets with early-bird windows (`sale_end` is days before the start), general admission, free, donation, online. Group bookings, promo codes, affiliate links, and waitlists on sold-out events. Titles are unique and never reuse a title of `seed_data` or `seed_showcase`.

With `--organizer <username>` (an existing organizer account), 20 of the 60 events are created for that user (`mine` in `demo_kz_data.EVENTS`): past, running, upcoming, a draft, a pending, a rejected and a cancelled one. The rest belong to the demo organizers.

### Sales and money

- Purchases run from the event's publication to its start: an early-bird burst, a quiet middle, a rise in the last week, a few on the day. Times of day are weighted towards evenings and lunch breaks, with few at night. Each sale is tied to an attendee who had already signed up.
- Roughly 8 000 tickets and 7 500 payments: completed, pending (about a dozen live holds on events within three weeks, plus group-booking holds, all younger than ten minutes), failed (`card_declined`, mostly, and `insufficient_funds`), expired holds, full refunds, partial refunds, and 8 disputes.
- Refund requests in every state: open (only for upcoming events), approved (with the refund), rejected (the ticket stays valid).
- Reviews only for ended events and only from attendees whose ticket was scanned; about 80 % are 4-5 stars, with a few critical ones; comments in ru, kk and en.
- Check-ins through gates (a main entrance, and a VIP entrance where there are VIP tickets), each logged with the staff member who scanned it.
- Amounts go through the real pricing code (`events.billing`, `events.seat_pricing`, `bookings.payments`). `Payment.paid_at` and `Booking.confirmed_at` are set to the day the money arrived, so the sales chart and analytics agree; the dashboard's per-event numbers equal `GET /events/{id}/analytics/` (asserted in tests), and `manage.py run_sql_checks` reports nothing.

## Running it on the server

```bash
# 1. Back up first (docs/DEPLOY.md, "Backups").
# 2. Seed (hashing 780 passwords takes about 40 s on 8 cores, 2.5 minutes on one; the rest is under 10 s):
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend \
  python manage.py seed_demo_kz --i-know-this-is-a-demo --organizer organizer \
  --credentials-file /tmp/demo-credentials.txt
# 3. Copy the credentials file out of the container to the deploy user's home (mode 0600),
#    then delete it inside the container.
# 4. Index the new events for search:
docker compose ... exec -T backend python manage.py index_events
```

Hashing uses a process pool (`concurrent.futures.ProcessPoolExecutor`) when it would take more than two seconds, and falls back to one process where no pool can start. Progress lines show counts only.

Re-running is safe: users, categories and events are found by natural key (user name, category name, event title), and an existing event is left as it is, so a second run creates nothing (and needs a new, empty credentials file name; keep the first file, it holds the only copy of the passwords). Run it with the same `--organizer` as the first time: the second run does not move events between owners.

## Removing it

```bash
docker compose ... exec -T backend python manage.py seed_demo_kz --i-know-this-is-a-demo --remove --dry-run --organizer organizer
docker compose ... exec -T backend python manage.py seed_demo_kz --i-know-this-is-a-demo --remove --organizer organizer
```

Pass the same `--organizer` as when seeding: without it the owner's 20 events are not recognised and stay (the command says so). In one transaction, in an order the PROTECT foreign keys allow, it deletes: provider events, refunds, payments, booking seats, bookings, check-in logs and lists, refund requests, registrations, waitlist entries, reviews, promo codes, affiliates, event staff (including the co-organizer roles of `--organizer`), ticket types, seat maps (and their seats), events, and the demo users (with their profiles and notifications). `--dry-run` prints the per-model counts and deletes nothing.

What is found as "created by the command": events whose title is in `demo_kz_data.EVENTS` and whose owner is a demo user (`kz_` name on `demo.eventhub.local`) or the `--organizer`; users by that name and domain. Never touched: real users and events, categories (shared), and anything else. Kept and reported: a demo event that a real account bought a ticket for (money records must never disappear; its demo buyers stay with it), and a demo user who owns or holds a ticket for something that is not removed.
