-- name: group_booking_inconsistent
-- severity: CRITICAL
-- invariant: A holding or confirmed group booking has 1..8 seats
--   (MAX_GROUP_SEATS); a cancelled, expired or refunded one has none (its
--   seats are deleted when released); a holding booking has a hold deadline;
--   a confirmed one records amount_paid, and its payment (if any) charged
--   exactly that amount.
-- why: Booking seats are tickets and count against capacity. Seats left on a
--   dead booking block the hall; a confirmed booking without seats or with a
--   payment that disagrees with amount_paid breaks refunds and revenue.
WITH seat_counts AS (
    SELECT booking_id, count(*) AS seats
    FROM bookings_bookingseat
    GROUP BY booking_id
)
SELECT 'booking:' || b.id AS ref,
       b.event_id,
       b.status,
       COALESCE(sc.seats, 0) AS seats,
       b.amount_paid,
       p.amount AS payment_amount,
       CASE
           WHEN b.status IN ('holding', 'confirmed') AND COALESCE(sc.seats, 0) = 0 THEN 'live booking without seats'
           WHEN b.status IN ('holding', 'confirmed') AND sc.seats > 8 THEN 'more than 8 seats'
           WHEN b.status IN ('cancelled', 'expired', 'refunded') AND COALESCE(sc.seats, 0) > 0
               THEN b.status || ' booking still holds seats'
           WHEN b.status = 'holding' AND b.hold_expires_at IS NULL THEN 'holding booking without hold deadline'
           WHEN b.status = 'confirmed' AND b.amount_paid IS NULL THEN 'confirmed booking without amount_paid'
           WHEN b.amount_paid IS NOT NULL AND p.id IS NOT NULL AND p.amount <> b.amount_paid
               THEN 'payment amount differs from amount_paid'
       END AS problem
FROM bookings_booking b
LEFT JOIN seat_counts sc ON sc.booking_id = b.id
LEFT JOIN payments_payment p ON p.booking_id = b.id
WHERE (b.status IN ('holding', 'confirmed') AND (COALESCE(sc.seats, 0) = 0 OR sc.seats > 8))
   OR (b.status IN ('cancelled', 'expired', 'refunded') AND COALESCE(sc.seats, 0) > 0)
   OR (b.status = 'holding' AND b.hold_expires_at IS NULL)
   OR (b.status = 'confirmed' AND b.amount_paid IS NULL)
   OR (b.amount_paid IS NOT NULL AND p.id IS NOT NULL AND p.amount <> b.amount_paid)
ORDER BY 1;
