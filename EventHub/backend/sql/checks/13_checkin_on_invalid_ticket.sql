-- name: checkin_on_invalid_ticket
-- severity: CRITICAL
-- invariant: Only valid tickets are checked in: a checked-in registration is
--   confirmed, has checked_in_at and its event is not cancelled; a checked-in
--   group-booking seat belongs to a confirmed booking.
-- why: check_in_registration refuses pending, cancelled and refunded tickets
--   and cancelled events. A row here is either someone let in without a valid
--   ticket or a ticket refunded after it was used (money returned for a
--   delivered service).
SELECT 'registration:' || r.id AS ref,
       r.event_id,
       r.status AS ticket_status,
       e.status AS event_status,
       CASE
           WHEN r.status <> 'confirmed' THEN 'checked in with ticket status ' || r.status
           WHEN r.checked_in_at IS NULL THEN 'checked in without checked_in_at'
           ELSE 'checked in to a cancelled event'
       END AS problem
FROM events_registration r
JOIN events_event e ON e.id = r.event_id
WHERE r.is_checked_in
  AND (r.status <> 'confirmed' OR r.checked_in_at IS NULL OR e.status = 'cancelled')
UNION ALL
SELECT 'booking_seat:' || bs.id,
       b.event_id,
       b.status,
       e.status,
       'checked in on a ' || b.status || ' group booking'
FROM bookings_bookingseat bs
JOIN bookings_booking b ON b.id = bs.booking_id
JOIN events_event e ON e.id = b.event_id
WHERE bs.is_checked_in
  AND b.status <> 'confirmed'
ORDER BY 1;
