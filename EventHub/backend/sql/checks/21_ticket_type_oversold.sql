-- name: ticket_type_oversold
-- severity: CRITICAL
-- invariant: A ticket tier with a quantity has at most that many live
--   (pending or confirmed) registrations.
-- why: register_for_event row-locks the tier and compares sold with quantity;
--   more live tickets than the tier allows is an oversell of e.g. the VIP
--   zone even when the event as a whole still has room.
SELECT tt.id AS ticket_type_id,
       tt.event_id,
       tt.name,
       tt.quantity,
       count(r.id) AS live_registrations
FROM events_tickettype tt
JOIN events_registration r
  ON r.ticket_type_id = tt.id AND r.status IN ('pending', 'confirmed')
WHERE tt.quantity IS NOT NULL
GROUP BY tt.id, tt.event_id, tt.name, tt.quantity
HAVING count(r.id) > tt.quantity
ORDER BY tt.id;
