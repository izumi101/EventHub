-- name: money_kept_for_void_ticket
-- severity: CRITICAL
-- invariant: A completed payment whose ticket is void (registration cancelled
--   or rejected; group booking cancelled, expired or refunded) has been
--   refunded in full.
-- why: The buyer paid and has no ticket. refund_payment cancels the
--   registration only after a full refund, and confirm_payment refunds a
--   payment that arrives after the hold ended; a row here is money we owe.
--   (Booking payments that payments/0005 imported with needs_review land here
--   on purpose.)
SELECT p.id AS payment_id,
       'registration:' || r.id AS target,
       r.status AS target_status,
       p.status AS payment_status,
       p.amount,
       p.refunded_amount
FROM payments_payment p
JOIN events_registration r ON r.id = p.registration_id
WHERE r.status IN ('cancelled', 'rejected')
  AND p.status = 'completed'
  AND p.refunded_amount < p.amount
UNION ALL
SELECT p.id,
       'booking:' || b.id,
       b.status,
       p.status,
       p.amount,
       p.refunded_amount
FROM payments_payment p
JOIN bookings_booking b ON b.id = p.booking_id
WHERE b.status IN ('cancelled', 'expired', 'refunded')
  AND p.status = 'completed'
  AND p.refunded_amount < p.amount
ORDER BY 1;
