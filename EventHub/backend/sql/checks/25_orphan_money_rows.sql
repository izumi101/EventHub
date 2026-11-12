-- name: orphan_money_rows
-- severity: CRITICAL
-- invariant: Every payment pays for exactly one thing (a registration or a
--   group booking); a refund without a payment is an orphan refund that names
--   the provider and its payment id; a succeeded refund belongs to a payment
--   that took the money (completed, refunded or disputed).
-- why: Money rows are PROTECTed and must never lose their subject. The check
--   constraints payment_exactly_one_target / refund_payment_or_orphan_target
--   enforce the first two today; the third is only kept by the service layer.
SELECT 'payment:' || p.id AS ref,
       'payment without registration and booking' AS problem
FROM payments_payment p
WHERE p.registration_id IS NULL AND p.booking_id IS NULL
UNION ALL
SELECT 'payment:' || p.id,
       'payment for both a registration and a booking'
FROM payments_payment p
WHERE p.registration_id IS NOT NULL AND p.booking_id IS NOT NULL
UNION ALL
SELECT 'refund:' || rf.id,
       'refund without payment that is not a complete orphan refund'
FROM payments_refund rf
WHERE rf.payment_id IS NULL
  AND (rf.kind <> 'orphan' OR rf.provider = '' OR rf.provider_payment_id = '')
UNION ALL
SELECT 'refund:' || rf.id,
       'succeeded refund of a ' || p.status || ' payment'
FROM payments_refund rf
JOIN payments_payment p ON p.id = rf.payment_id
WHERE rf.status = 'succeeded'
  AND p.status NOT IN ('completed', 'refunded', 'disputed')
ORDER BY 1;
