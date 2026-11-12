-- What the recommended indexes would change, measured inside a transaction
-- that is ROLLED BACK: nothing is created permanently. Needs the schema owner
-- (CREATE INDEX) and should only run on a copy of the database, e.g.
--   CREATE DATABASE eventhub_scale TEMPLATE eventhub;   -- with no one connected
--   psql -h db -U eventhub_user -d eventhub_scale -f sql/explain/index_experiment.sql
-- The recommendations themselves are in docs/reports/database-checks-report.md;
-- they belong in a migration of the payments / bookings / events apps.

\pset pager off
SELECT stripe_checkout_session_id AS session_id
FROM payments_payment WHERE stripe_checkout_session_id <> '' ORDER BY id DESC LIMIT 1 \gset
SELECT stripe_session_id AS booking_session FROM bookings_booking WHERE stripe_session_id <> '' ORDER BY created_at DESC LIMIT 1 \gset

BEGIN;

CREATE INDEX tmp_payment_stripe_session ON payments_payment (stripe_checkout_session_id)
    WHERE stripe_checkout_session_id <> '';
CREATE INDEX tmp_booking_stripe_session ON bookings_booking (stripe_session_id)
    WHERE stripe_session_id <> '';
CREATE INDEX tmp_event_published_date ON events_event (date DESC) WHERE status = 'published';
ANALYZE payments_payment, bookings_booking, events_event;

\echo '== 1 with index: payment by legacy Stripe checkout session'
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id, p.registration_id, p.status, p.amount
FROM payments_payment p
WHERE p.stripe_checkout_session_id = :'session_id';

\echo '== 3 with index: group booking by Stripe session'
EXPLAIN (ANALYZE, BUFFERS)
SELECT b.id, b.status
FROM bookings_booking b
WHERE b.stripe_session_id = :'booking_session'
ORDER BY b.created_at DESC;

\echo '== 4 with index: event list first page'
EXPLAIN (ANALYZE, BUFFERS)
SELECT e.id, e.title, e.date, e.price, e.currency,
       COALESCE((SELECT count(u0.id) FROM events_registration u0
                 WHERE u0.event_id = e.id AND NOT (u0.status IN ('cancelled', 'rejected'))
                 GROUP BY u0.event_id), 0) AS active_registrations,
       COALESCE((SELECT count(u0.id) FROM bookings_bookingseat u0
                 JOIN bookings_booking u1 ON u0.booking_id = u1.id
                 WHERE u1.event_id = e.id AND u1.status IN ('holding', 'confirmed')
                 GROUP BY u1.event_id), 0) AS booked_seats,
       au.username, c.name
FROM events_event e
JOIN auth_user au ON e.organizer_id = au.id
LEFT JOIN events_category c ON e.category_id = c.id
WHERE e.status = 'published'
ORDER BY e.date DESC
LIMIT 12;

ROLLBACK;
