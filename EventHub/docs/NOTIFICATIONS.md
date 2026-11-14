# Notifications

## Agent Entry

- Purpose: how user notifications (in-app + email) work, which events send them, and how to configure SMTP.
- Read when: adding a notification type or trigger, changing an email, debugging a missing email, setting up SMTP.
- Skip when: you only need the payment flows themselves (`docs/payments/`).
- Canonical: Yes.
- Read next: `backend/notifications/` (code), `backend/jobs/queue.py` (outbox), `docs/DEMO.md`.

## Model

Every notification goes through one function:

```python
from notifications import types
from notifications.service import notify

notify(user, types.TICKET_PURCHASED, event=event, registration=reg, amount=payment.amount, currency='KZT')
```

`notify()` (`backend/notifications/service.py`):

1. builds the message for the type (`notifications/messages.py`: in-app title/body and the email content),
2. writes the in-app row (`events.Notification`, table `events_notification`, shown under the bell in the top bar),
3. if the user has an email address and the email of this type is on, renders the HTML + plain-text email and writes a `send_email` job (transactional outbox, `jobs/queue.py`).

Steps 2 and 3 run in a savepoint inside the caller's transaction: a notification exists if and only if the business change that caused it was committed, and a rollback leaves neither the row nor the email. `notify()` never raises: a failure is logged and rolls back only the notification. The worker (`manage.py run_worker`) sends the email after the commit, at least once, retrying with backoff.

Security emails — sign-up code, password reset code, the "sign-up attempt" heads-up, organizer account, 2FA codes — are not notifications. `accounts` sends them with `jobs.handlers.enqueue_email` directly; they are always sent and are not listed in the preferences.

## Types and triggers

| Type | Sent to | Trigger (code) | Email |
|---|---|---|---|
| `ticket_purchased` | buyer | paid ticket confirmed: Freedom Pay callback, Stripe webhook/verify, mock checkout, offline payment (`payments.services._confirm_paid_registration`) | e-ticket: event, date, venue, seat, ticket type, amount, QR |
| `registration_confirmed` | attendee | free registration (`events.services.registration.register_for_event`) | e-ticket with QR |
| `payment_failed` | buyer | Freedom Pay declines the payment; a payment arrives after the hold ended (it is refunded, see below) (`payments.freedompay_flow`) | optional |
| `payment_refunded` | buyer | any refund that returns money: organizer refund (`payments.services.refund_payment`), automatic late / duplicate / amount-mismatch refunds once the gateway confirms them (`freedompay_flow._finish_refund`), Stripe late payments, group booking refunds | **always** |
| `refund_requested` | organizer | attendee asks for a refund (`events.services.refunds.request_refund`) | optional |
| `refund_approved` / `refund_rejected` | attendee | organizer resolves the request (`resolve_refund_request`); an approval sends this one notice, not a second "refunded" one | optional |
| `event_updated` | ticket holders | date, end, venue, address or online link of a published event changes (`events.services.lifecycle.update_event`); shows old → new | optional |
| `event_cancelled` | ticket holders | organizer cancels (`cancel_event`): one notice per person with the refund outcome (refunded / not refunded automatically) | **always** |
| `seat_available` | next on the waitlist | a spot is offered (`events.waitlist.promote_waitlist`) | optional |
| `group_booking_confirmed` | booking owner | group booking paid (`bookings.services.confirm_booking`) | QR of every seat (up to 10 inline) |
| `group_booking_claimed` | friend | a signed-in friend claims a seat of a paid booking, or the booking they claimed in gets paid (`claim_seat`, `confirm_booking`) | QR of the seat |
| `event_reminder` | ticket holders | 24 hours before the start (below) | optional |
| `organizer_message` | chosen audience | organizer broadcast (`events.messaging.broadcast_to_attendees`) | optional |
| `review_reminder` | — | defined, no trigger yet | in-app only |

"Ticket holders" (`service.ticket_holders`) are users with a confirmed registration, owners of confirmed group bookings and friends who claimed a seat in one — each person once.

Adding a type: add it to `notifications/types.py`, write its builder in `messages.py` (all strings through `gettext`), call `notify()` from the business code inside its transaction, run `makemigrations` (the `type` choices change) and regenerate the OpenAPI schema and frontend types.

## Email rendering

- One layout for every type: `notifications/templates/notifications/email/message.html` (table layout, inline CSS, escaped user content) and `message.txt` (plain-text alternative).
- Ticket QR codes encode `<FRONTEND_URL>/validate/<ticket_uuid>`, the same URL the frontend's ticket QR uses, so the door scanner accepts both. They are rendered with `segno` as PNG and attached inline (`Content-ID`, `<img src="cid:ticket-qr-N">`, `multipart/related`).
- Footer: a link to the preferences page `<FRONTEND_URL>/profile/notifications`, also sent as `List-Unsubscribe`. Mandatory emails say so.
- Dates use `NOTIFICATION_TIME_ZONE` (default `TIME_ZONE`, i.e. UTC), e.g. `Sat, 14 Nov 2026, 15:42 (Asia/Almaty)`.
- i18n: copy is in `gettext` / `{% translate %}`; adding ru/kk is a translation task (`makemessages`), not a code change. Emails are rendered in the server's active language today.

`jobs.handlers.send_email` accepts `html_body`, `attachments` (`{filename, mimetype, content_b64[, cid]}`) and `headers`. It allows only PNG/JPEG/PDF/iCalendar, at most 10 attachments of 256 KB each, safe file names and content ids, and only the `List-Unsubscribe` headers; line breaks are stripped from the subject. A malformed payload fails the job permanently (`PermanentJobError`) instead of being retried. Old payloads (subject/body only) still work.

## Preferences

`GET /api/v1/auth/profile/notifications/` → the address emails go to and, per type, `label`, `description`, `email_enabled`, `email_optional`.

`PATCH /api/v1/auth/profile/notifications/` with `{"email": {"event_reminder": false}}` changes only the listed types (JSON only). Types that are not optional (`event_cancelled`, `payment_refunded`) and unknown keys are rejected with 400. Authenticated users only, each sees and changes only their own settings.

Storage: `notifications.NotificationPreference` keeps only the opt-outs (`email_disabled`), so a new type is on by default and a mandatory type can never be switched off by stale data. In-app notifications are always created.

Frontend: `/profile/notifications` (`components/notification-preferences`), linked from the profile page; switches save immediately.

## 24-hour reminders

`notifications.reminders.send_due_reminders()` notifies every ticket holder of each published event starting in the next 24 hours. It runs every minute inside the worker's maintenance pass (`run_maintenance`) and on demand:

```bash
docker compose exec backend python manage.py send_event_reminders   # safe to run any number of times
```

Idempotency: each reminder is recorded in `notifications_sentreminder` (unique on user, event, kind, event start) in the same transaction as its notification and email job. A second pass — or a second worker at the same moment — cannot insert the row again, so nothing is sent twice. If the notification fails, the record is rolled back and the next pass retries. A rescheduled event (new start) gets a new reminder; cancelled events get none.

## SMTP

Without `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` the console backend prints every email (MIME source, HTML included) in the **worker** log: `docker compose logs -f worker`. Tests use the locmem backend.

For real delivery set in `.env` (see the comments in `.env.example`), then restart backend and worker:

| Provider | Settings |
|---|---|
| Mailtrap (demo: catches all mail in a test inbox) | `EMAIL_HOST=sandbox.smtp.mailtrap.io`, `EMAIL_PORT=587`, user/password from the inbox |
| Gmail | `EMAIL_HOST=smtp.gmail.com`, `EMAIL_HOST_USER=<you>@gmail.com`, `EMAIL_HOST_PASSWORD=<app password>` (2-Step Verification required) |
| Brevo | `EMAIL_HOST=smtp-relay.brevo.com`, SMTP login + SMTP key, `DEFAULT_FROM_EMAIL` = a verified sender |

`EMAIL_BACKEND` overrides the choice; `EMAIL_USE_TLS=1` (STARTTLS on 587) is the default. With `DJANGO_DEBUG=0` the backend refuses to start without SMTP.

## Troubleshooting

- No email, but the bell shows the notification: the user switched the type off, has no address, or the job failed — check `jobs_job` (`kind='send_email'`, `status`, `last_error`) in Django admin, and `manage.py run_sql_checks` (`outbox_jobs_stuck`).
- No notification at all: the business transaction rolled back, or `notify()` logged an exception (`notifications.service` logger).

## Open items

- PDF ticket attachment and Apple/Google Wallet passes (roadmap phase 8); web push and SMS (phase 2 follow-up).
- Stripe `checkout.session.async_payment_failed` / `charge.refunded` events do not notify yet: the full Stripe event set waits for the Stripe move onto the provider layer (`docs/HANDOFF.md`).
- One-click unsubscribe without signing in (signed token, `List-Unsubscribe-Post`) — today the link opens the preferences page.
- Emails are rendered in the server language; per-user language comes with i18n (phase 8).
