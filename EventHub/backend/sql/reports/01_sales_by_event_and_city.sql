-- Sales per event and per city (read-only; run as eventhub_readonly).
-- Tickets = confirmed registrations + seats of confirmed group bookings.
-- Net revenue = money taken (completed / refunded / disputed payments) minus
-- refunds, in the event currency. City = last part of "Venue, City".
WITH payments AS (
    SELECT COALESCE(r.event_id, b.event_id) AS event_id,
           sum(p.amount) FILTER (WHERE p.status IN ('completed', 'refunded', 'disputed')) AS gross,
           sum(p.refunded_amount) AS refunded
    FROM payments_payment p
    LEFT JOIN events_registration r ON r.id = p.registration_id
    LEFT JOIN bookings_booking b ON b.id = p.booking_id
    GROUP BY 1
), tickets AS (
    SELECT event_id, count(*) AS tickets
    FROM (
        SELECT event_id FROM events_registration WHERE status = 'confirmed'
        UNION ALL
        SELECT b.event_id FROM bookings_bookingseat bs JOIN bookings_booking b ON b.id = bs.booking_id
        WHERE b.status = 'confirmed'
    ) t
    GROUP BY event_id
), per_event AS (
    SELECT CASE WHEN e.is_online THEN 'Online' ELSE trim(regexp_replace(e.location, '^.*,', '')) END AS city,
           e.title,
           e.currency,
           COALESCE(t.tickets, 0) AS tickets,
           COALESCE(p.gross, 0) - COALESCE(p.refunded, 0) AS net_revenue
    FROM events_event e
    LEFT JOIN tickets t ON t.event_id = e.id
    LEFT JOIN payments p ON p.event_id = e.id
    WHERE e.status IN ('published', 'completed', 'cancelled')
)
SELECT COALESCE(city, 'ALL CITIES') AS city,
       COALESCE(title, '— city total —') AS event,
       currency,
       sum(tickets) AS tickets,
       sum(net_revenue) AS net_revenue
FROM per_event
GROUP BY GROUPING SETS ((city, title, currency), (city, currency), (currency))
ORDER BY currency, city NULLS LAST, title NULLS FIRST;
