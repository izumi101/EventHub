-- name: payment_amounts_invalid
-- severity: CRITICAL
-- invariant: 0 <= refunded_amount <= amount; status 'refunded' means
--   refunded_amount = amount and a completed payment is never fully refunded
--   (refund_payment switches it to 'refunded'); only a payment that took the
--   money can carry a refund, and a refund records when it happened.
-- why: These two columns are the money ledger until the Refund table takes
--   over (ADR 0001). A refund larger than the charge, or a status that
--   contradicts the amounts, makes revenue reports and refund buttons wrong.
SELECT payment_id, status, amount, refunded_amount, problem
FROM (
    SELECT p.id AS payment_id,
           p.status,
           p.amount,
           p.refunded_amount,
           CASE
               WHEN p.amount < 0 THEN 'negative amount'
               WHEN p.refunded_amount < 0 THEN 'negative refunded_amount'
               WHEN p.refunded_amount > p.amount THEN 'refunded more than was paid'
               WHEN p.status = 'refunded' AND p.refunded_amount <> p.amount THEN 'status refunded but refund is partial'
               WHEN p.status = 'completed' AND p.amount > 0 AND p.refunded_amount = p.amount
                   THEN 'fully refunded but status still completed'
               WHEN p.status IN ('pending', 'failed', 'expired') AND p.refunded_amount > 0
                   THEN 'refund recorded on a payment that never completed'
               WHEN p.refunded_amount > 0 AND p.refunded_at IS NULL THEN 'refund without refunded_at'
           END AS problem
    FROM payments_payment p
) checked
WHERE problem IS NOT NULL
ORDER BY payment_id;
