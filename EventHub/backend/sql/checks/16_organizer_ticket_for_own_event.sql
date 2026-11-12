-- name: organizer_ticket_for_own_event
-- severity: CRITICAL
-- invariant: Business rule (AGENTS.md): an organizer never holds a live ticket
--   (pending/confirmed registration or holding/confirmed group booking) for
--   an event they organise.
-- why: ensure_attendee_can_buy enforces it in the purchase paths; a row here
--   came through another path (admin, import, a bug) and inflates sales and
--   attendance with the organizer's own tickets.
SELECT 'registration:' || r.id AS ref,
       r.event_id,
       r.user_id AS organizer_id,
       r.status
FROM events_registration r
JOIN events_event e ON e.id = r.event_id
WHERE r.user_id = e.organizer_id
  AND r.status IN ('pending', 'confirmed')
UNION ALL
SELECT 'booking:' || b.id,
       b.event_id,
       b.owner_id,
       b.status
FROM bookings_booking b
JOIN events_event e ON e.id = b.event_id
WHERE b.owner_id = e.organizer_id
  AND b.status IN ('holding', 'confirmed')
ORDER BY 1;
