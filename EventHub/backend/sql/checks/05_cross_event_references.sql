-- name: cross_event_references
-- severity: CRITICAL
-- invariant: Everything a ticket points to belongs to the ticket's own event:
--   the seat (via its seat map), the ticket type, the promo code, the
--   affiliate; and every seat of a group booking belongs to the booking's event.
-- why: These foreign keys are nullable and not scoped to the event in the
--   schema. A ticket priced from another event's tier or seated in another
--   event's hall is charged wrongly and breaks capacity accounting.
SELECT 'registration:' || r.id AS ref, 'seat belongs to event ' || sm.event_id AS problem, r.event_id
FROM events_registration r
JOIN events_eventseat s ON s.id = r.seat_id
JOIN events_seatmap sm ON sm.id = s.seat_map_id
WHERE sm.event_id <> r.event_id
UNION ALL
SELECT 'registration:' || r.id, 'ticket type belongs to event ' || tt.event_id, r.event_id
FROM events_registration r
JOIN events_tickettype tt ON tt.id = r.ticket_type_id
WHERE tt.event_id <> r.event_id
UNION ALL
SELECT 'registration:' || r.id, 'promo code belongs to event ' || pc.event_id, r.event_id
FROM events_registration r
JOIN events_promocode pc ON pc.id = r.promo_code_id
WHERE pc.event_id <> r.event_id
UNION ALL
SELECT 'registration:' || r.id, 'affiliate belongs to event ' || a.event_id, r.event_id
FROM events_registration r
JOIN events_affiliate a ON a.id = r.affiliate_id
WHERE a.event_id <> r.event_id
UNION ALL
SELECT 'booking:' || b.id, 'seat ' || bs.seat_id || ' belongs to event ' || sm.event_id, b.event_id
FROM bookings_bookingseat bs
JOIN bookings_booking b ON b.id = bs.booking_id
JOIN events_eventseat s ON s.id = bs.seat_id
JOIN events_seatmap sm ON sm.id = s.seat_map_id
WHERE sm.event_id <> b.event_id
ORDER BY 1;
