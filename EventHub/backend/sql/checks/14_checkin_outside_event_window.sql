-- name: checkin_outside_event_window
-- severity: WARNING
-- invariant: Check-ins happen around the event: from 3 hours before the start
--   to 2 hours after the end (end_date, or start + 6 hours when it is not
--   set), and never in the future.
-- why: A scan days before or after the event is a reused / leaked QR code or
--   a clock problem on a scanner; it also distorts attendance statistics.
SELECT 'registration:' || r.id AS ref,
       r.event_id,
       e.date AS event_start,
       r.checked_in_at
FROM events_registration r
JOIN events_event e ON e.id = r.event_id
WHERE r.is_checked_in
  AND r.checked_in_at IS NOT NULL
  AND (r.checked_in_at < e.date - interval '3 hours'
       OR r.checked_in_at > COALESCE(e.end_date, e.date + interval '6 hours') + interval '2 hours'
       OR r.checked_in_at > now())
UNION ALL
SELECT 'booking_seat:' || bs.id,
       b.event_id,
       e.date,
       bs.checked_in_at
FROM bookings_bookingseat bs
JOIN bookings_booking b ON b.id = bs.booking_id
JOIN events_event e ON e.id = b.event_id
WHERE bs.is_checked_in
  AND bs.checked_in_at IS NOT NULL
  AND (bs.checked_in_at < e.date - interval '3 hours'
       OR bs.checked_in_at > COALESCE(e.end_date, e.date + interval '6 hours') + interval '2 hours'
       OR bs.checked_in_at > now())
ORDER BY 1;
