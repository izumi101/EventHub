-- name: review_without_attendance
-- severity: WARNING
-- invariant: A review has a rating from 1 to 5, is written after the event
--   started, by someone who had a confirmed ticket for it (own registration,
--   or a seat they own or claimed in a confirmed group booking).
-- why: Ratings feed the event page and the organizer ranking. Reviews from
--   non-attendees or before the event are fake or spam.
SELECT rv.id AS review_id,
       rv.event_id,
       rv.user_id,
       rv.rating,
       CASE
           WHEN rv.rating NOT BETWEEN 1 AND 5 THEN 'rating out of range'
           WHEN rv.created_at < e.date THEN 'written before the event started'
           ELSE 'reviewer had no confirmed ticket'
       END AS problem
FROM events_review rv
JOIN events_event e ON e.id = rv.event_id
WHERE rv.rating NOT BETWEEN 1 AND 5
   OR rv.created_at < e.date
   OR NOT (
        EXISTS (SELECT 1 FROM events_registration r
                WHERE r.user_id = rv.user_id AND r.event_id = rv.event_id AND r.status = 'confirmed')
        OR EXISTS (SELECT 1 FROM bookings_booking b
                   JOIN bookings_bookingseat bs ON bs.booking_id = b.id
                   WHERE b.event_id = rv.event_id AND b.status = 'confirmed'
                     AND (b.owner_id = rv.user_id OR bs.claimed_by_id = rv.user_id)))
ORDER BY rv.id;
