-- Hot queries of the API, as the Django ORM sends them, with EXPLAIN (ANALYZE, BUFFERS).
-- Read-only: run it as the read-only role, e.g.
--   psql -h db -U eventhub_readonly -d eventhub -f sql/explain/hot_queries.sql
-- The parameter values are taken from the data first (\gset), so the plans use
-- real ids. Column lists are shortened to `*`-free projections of the same
-- tables; filters, joins, ordering and limits are exactly the ORM's
-- (captured with CaptureQueriesContext on the endpoints, see
-- docs/reports/database-checks-report.md).

\pset pager off

SELECT stripe_checkout_session_id AS session_id, provider_session_id AS provider_session
FROM payments_payment WHERE stripe_checkout_session_id <> '' ORDER BY id DESC LIMIT 1 \gset
SELECT stripe_session_id AS booking_session FROM bookings_booking WHERE stripe_session_id <> '' ORDER BY created_at DESC LIMIT 1 \gset
SELECT user_id AS busy_user FROM events_registration GROUP BY user_id ORDER BY count(*) DESC, user_id LIMIT 1 \gset

\echo '== 1. Payment by legacy Stripe checkout session (payments/services.py confirm_payment, success page)'
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id, p.registration_id, p.status, p.amount
FROM payments_payment p
WHERE p.stripe_checkout_session_id = :'session_id';

\echo '== 2. Payment by provider session (provider layer, ADR 0001)'
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id, p.registration_id, p.status, p.amount
FROM payments_payment p
WHERE p.provider = 'mock' AND p.provider_session_id = :'provider_session';

\echo '== 3. Group booking by Stripe session (bookings/payments.py webhook, bookings/views.py success page)'
EXPLAIN (ANALYZE, BUFFERS)
SELECT b.id, b.status
FROM bookings_booking b
WHERE b.stripe_session_id = :'booking_session'
ORDER BY b.created_at DESC;

\echo '== 4. Event list, first page (GET /api/v1/events/: published, newest first, with capacity counts)'
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

\echo '== 5. My registrations, first page (GET /api/v1/my-registrations/)'
EXPLAIN (ANALYZE, BUFFERS)
SELECT r.id, r.status, r.registered_at, p.status AS payment_status, tt.name, s.row, s.col
FROM events_registration r
JOIN auth_user au ON r.user_id = au.id
LEFT JOIN events_eventseat s ON r.seat_id = s.id
LEFT JOIN events_seatmap sm ON s.seat_map_id = sm.id
LEFT JOIN events_promocode pc ON r.promo_code_id = pc.id
LEFT JOIN events_tickettype tt ON r.ticket_type_id = tt.id
LEFT JOIN events_refundrequest rr ON r.id = rr.registration_id
LEFT JOIN payments_payment p ON r.id = p.registration_id
WHERE r.user_id = :busy_user AND NOT (r.status = 'cancelled')
ORDER BY r.registered_at DESC
LIMIT 12;
