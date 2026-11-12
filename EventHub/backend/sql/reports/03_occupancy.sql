-- Occupancy per event (read-only): live tickets against capacity.
-- live = confirmed + pending registrations + seats of holding / confirmed
-- group bookings (what Event.available_spots subtracts).
WITH live AS (
    SELECT event_id,
           count(*) FILTER (WHERE status = 'confirmed') AS confirmed,
           count(*) FILTER (WHERE status = 'pending') AS on_hold
    FROM events_registration
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
       e.status,
       e.max_participants AS capacity,
       COALESCE(l.confirmed, 0) AS confirmed,
       COALESCE(l.on_hold, 0) AS on_hold,
       COALESCE(s.booked_seats, 0) AS group_seats,
       round(100.0 * (COALESCE(l.confirmed, 0) + COALESCE(l.on_hold, 0) + COALESCE(s.booked_seats, 0))
             / NULLIF(e.max_participants, 0), 1) AS occupancy_pct
FROM events_event e
LEFT JOIN live l ON l.event_id = e.id
LEFT JOIN seats s ON s.event_id = e.id
WHERE e.status IN ('published', 'completed')
ORDER BY occupancy_pct DESC NULLS LAST, e.id;
