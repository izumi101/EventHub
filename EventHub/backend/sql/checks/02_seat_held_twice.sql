-- name: seat_held_twice
-- severity: CRITICAL
-- invariant: A seat belongs to at most one live holder: one pending/confirmed
--   registration or one seat of a holding/confirmed group booking.
-- why: Two holders of one seat = the same seat sold (or held) twice; two
--   people arrive with tickets for one chair. The seat row lock in
--   register_for_event / create_booking should make this impossible.
WITH holders AS (
    SELECT r.seat_id, 'registration:' || r.id AS holder
    FROM events_registration r
    WHERE r.seat_id IS NOT NULL
      AND r.status IN ('pending', 'confirmed')
    UNION ALL
    SELECT bs.seat_id, 'booking:' || bs.booking_id
    FROM bookings_bookingseat bs
    JOIN bookings_booking b ON b.id = bs.booking_id
    WHERE b.status IN ('holding', 'confirmed')
)
SELECT seat_id,
       count(*) AS holders,
       string_agg(holder, ', ' ORDER BY holder) AS held_by
FROM holders
GROUP BY seat_id
HAVING count(*) > 1
ORDER BY seat_id;
