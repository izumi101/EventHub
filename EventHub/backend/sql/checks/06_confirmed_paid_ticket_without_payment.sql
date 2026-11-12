-- name: confirmed_paid_ticket_without_payment
-- severity: CRITICAL
-- invariant: A confirmed registration that costs money (locked price > 0, or
--   a paid / donation tier, or a priced event without tiers) has a payment in
--   status completed (or disputed: money taken, chargeback open).
-- why: Confirmed means "valid ticket". Without a completed payment the ticket
--   was issued for free: revenue loss, or a payment flow that confirmed the
--   seat before the money arrived. Partially refunded payments stay
--   completed and do not match.
SELECT r.id AS registration_id,
       r.event_id,
       r.locked_price,
       tt.kind AS ticket_kind,
       p.id AS payment_id,
       COALESCE(p.status, 'missing') AS payment_status
FROM events_registration r
JOIN events_event e ON e.id = r.event_id
LEFT JOIN events_tickettype tt ON tt.id = r.ticket_type_id
LEFT JOIN payments_payment p ON p.registration_id = r.id
WHERE r.status = 'confirmed'
  AND CASE
          WHEN r.locked_price IS NOT NULL THEN r.locked_price > 0
          WHEN tt.id IS NOT NULL THEN tt.kind <> 'free' AND COALESCE(r.donation_amount, tt.price) > 0
          ELSE e.price > 0
      END
  AND (p.id IS NULL OR p.status NOT IN ('completed', 'disputed'))
ORDER BY r.id;
