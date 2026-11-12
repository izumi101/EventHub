-- name: seat_blocked_without_holder
-- severity: WARNING
-- invariant: A seat with is_available = false has a live holder (pending or
--   confirmed registration, or a seat in a holding/confirmed group booking).
-- why: A seat that is blocked but belongs to nobody is lost revenue: it is
--   never offered again. Usually a release path (hold expiry, cancellation,
--   refund) that forgot to free the seat.
SELECT s.id AS seat_id,
       sm.event_id,
       s.row,
       s.col
FROM events_eventseat s
JOIN events_seatmap sm ON sm.id = s.seat_map_id
WHERE NOT s.is_available
  AND NOT EXISTS (
        SELECT 1 FROM events_registration r
        WHERE r.seat_id = s.id AND r.status IN ('pending', 'confirmed'))
  AND NOT EXISTS (
        SELECT 1 FROM bookings_bookingseat bs
        JOIN bookings_booking b ON b.id = bs.booking_id
        WHERE bs.seat_id = s.id AND b.status IN ('holding', 'confirmed'))
ORDER BY s.id;
