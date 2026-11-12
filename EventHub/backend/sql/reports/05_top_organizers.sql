-- Top organizers by net revenue (read-only). Uses only the auth_user columns
-- the read-only role may see (never `password`). One row per organizer and
-- event currency: amounts in different currencies are never added up.
WITH money AS (
    SELECT COALESCE(r.event_id, b.event_id) AS event_id,
           sum(p.amount) FILTER (WHERE p.status IN ('completed', 'refunded', 'disputed'))
               - sum(p.refunded_amount) AS net
    FROM payments_payment p
    LEFT JOIN events_registration r ON r.id = p.registration_id
    LEFT JOIN bookings_booking b ON b.id = p.booking_id
    GROUP BY 1
), tickets AS (
    SELECT event_id,
           count(*) FILTER (WHERE status = 'confirmed') AS sold,
           count(*) FILTER (WHERE is_checked_in) AS checked_in
    FROM events_registration
    GROUP BY event_id
), ratings AS (
    SELECT event_id, sum(rating) AS rating_sum, count(*) AS reviews
    FROM events_review
    GROUP BY event_id
)
SELECT u.username,
       trim(u.first_name || ' ' || u.last_name) AS organizer,
       upper(e.currency) AS currency,
       count(*) AS events,
       COALESCE(sum(t.sold), 0) AS tickets_sold,
       COALESCE(sum(m.net), 0) AS net_revenue,
       round(sum(ra.rating_sum)::numeric / NULLIF(sum(ra.reviews), 0), 2) AS avg_rating,
       COALESCE(sum(ra.reviews), 0) AS reviews,
       round(100.0 * sum(t.checked_in) FILTER (WHERE e.status = 'completed')
             / NULLIF(sum(t.sold) FILTER (WHERE e.status = 'completed'), 0), 1) AS checkin_rate_pct
FROM auth_user u
JOIN events_event e ON e.organizer_id = u.id
LEFT JOIN money m ON m.event_id = e.id
LEFT JOIN tickets t ON t.event_id = e.id
LEFT JOIN ratings ra ON ra.event_id = e.id
GROUP BY u.username, organizer, upper(e.currency)
ORDER BY currency, net_revenue DESC, u.username
LIMIT 10;
