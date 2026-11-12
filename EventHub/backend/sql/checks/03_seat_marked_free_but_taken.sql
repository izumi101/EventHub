-- name: seat_marked_free_but_taken
-- severity: CRITICAL
-- invariant: A seat with a live holder (pending/confirmed registration or
--   holding/confirmed group booking) has events_eventseat.is_available = false.
-- why: The seat map and the purchase checks read is_available. A taken seat
--   shown as free will be sold again to the next buyer.
SELECT s.id AS seat_id,
       sm.event_id,
       s.row,
       s.col,
       COALESCE('registration:' || r.id, 'booking:' || bs.booking_id) AS held_by
FROM events_eventseat s
JOIN events_seatmap sm ON sm.id = s.seat_map_id
LEFT JOIN events_registration r
       ON r.seat_id = s.id AND r.status IN ('pending', 'confirmed')
LEFT JOIN bookings_bookingseat bs ON bs.seat_id = s.id
LEFT JOIN bookings_booking b
       ON b.id = bs.booking_id AND b.status IN ('holding', 'confirmed')
WHERE s.is_available
  AND (r.id IS NOT NULL OR b.id IS NOT NULL)
ORDER BY s.id;
