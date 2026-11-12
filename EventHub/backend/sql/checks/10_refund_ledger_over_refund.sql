-- name: refund_ledger_over_refund
-- severity: CRITICAL
-- invariant: For every payment, the refunds in status pending or succeeded add
--   up to at most payment.amount (payments.models.Refund docstring).
-- why: The refund job sends each pending row to the provider. Rows adding up
--   to more than the charge are an attempt to pay out more than we took in.
SELECT p.id AS payment_id,
       p.amount,
       sum(rf.amount) AS refunds_total,
       count(*) AS refunds,
       sum(rf.amount) - p.amount AS excess
FROM payments_payment p
JOIN payments_refund rf ON rf.payment_id = p.id
WHERE rf.status IN ('pending', 'succeeded')
GROUP BY p.id, p.amount
HAVING sum(rf.amount) > p.amount
ORDER BY excess DESC, p.id;
