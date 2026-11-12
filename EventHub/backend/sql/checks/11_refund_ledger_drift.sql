-- name: refund_ledger_drift
-- severity: WARNING
-- invariant: When a payment has rows in the Refund ledger, the succeeded ones
--   add up to payment.refunded_amount.
-- why: During the provider migration (ADR 0001) the legacy refund path only
--   updates payments_payment.refunded_amount while the new path writes Refund
--   rows. A difference means one of the two books is wrong; after the switch
--   the ledger is the source of truth. Payments without any ledger row
--   (legacy refunds) are not compared.
SELECT p.id AS payment_id,
       p.refunded_amount,
       COALESCE(sum(rf.amount) FILTER (WHERE rf.status = 'succeeded'), 0) AS ledger_succeeded,
       count(*) AS ledger_rows
FROM payments_payment p
JOIN payments_refund rf ON rf.payment_id = p.id
GROUP BY p.id, p.refunded_amount
HAVING COALESCE(sum(rf.amount) FILTER (WHERE rf.status = 'succeeded'), 0) <> p.refunded_amount
ORDER BY p.id;
