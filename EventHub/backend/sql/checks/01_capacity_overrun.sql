-- name: capacity_overrun
-- severity: CRITICAL
-- invariant: For every event, live registrations (pending holds + confirmed)
--   plus seats in live group bookings (holding + confirmed) never exceed
--   events_event.max_participants.
-- why: The app sells exactly max_participants spots (Event.available_spots,
--   register_for_event locks the event row). More live tickets than spots
--   means overselling: people with valid QR codes who cannot get in.
WITH regs AS (
    SELECT event_id, count(*) AS active_registrations
    FROM events_registration
    WHERE status IN ('pending', 'confirmed')
    GROUP BY event_id
), seats AS (
    SELECT b.event_id, count(*) AS booked_seats
    FROM bookings_bookingseat bs
    JOIN bookings_booking b ON b.id = bs.booking_id
    WHERE b.status IN ('holding', 'confirmed')
    GROUP BY b.event_id
)
SELECT e.id AS event_id,
       e.title,
       e.max_participants AS capacity,
       COALESCE(r.active_registrations, 0) AS active_registrations,
       COALESCE(s.booked_seats, 0) AS booked_seats,
       COALESCE(r.active_registrations, 0) + COALESCE(s.booked_seats, 0) - e.max_participants AS overrun
FROM events_event e
LEFT JOIN regs r ON r.event_id = e.id
LEFT JOIN seats s ON s.event_id = e.id
WHERE COALESCE(r.active_registrations, 0) + COALESCE(s.booked_seats, 0) > e.max_participants
ORDER BY overrun DESC, e.id;
