-- Money per currency and payment provider (read-only).
-- gross = charged (completed, refunded, disputed); refunded = refunded_amount;
-- open = still pending. Currency upper-cased: payments store 'kzt'.
-- provider '(none)': rows written by the legacy services, which do not fill
-- the provider columns yet (ADR 0001 expand step).
WITH p AS (
    SELECT upper(currency) AS currency, COALESCE(NULLIF(provider, ''), '(none)') AS provider,
           status, amount, refunded_amount
    FROM payments_payment
)
SELECT CASE WHEN GROUPING(currency) = 1 THEN 'ALL' ELSE currency END AS currency,
       CASE WHEN GROUPING(provider) = 1 THEN 'ALL' ELSE provider END AS provider,
       count(*) AS payments,
       count(*) FILTER (WHERE status = 'completed') AS completed,
       count(*) FILTER (WHERE status = 'refunded') AS refunded_full,
       count(*) FILTER (WHERE status = 'completed' AND refunded_amount > 0) AS refunded_partly,
       count(*) FILTER (WHERE status IN ('failed', 'expired')) AS failed_or_expired,
       sum(amount) FILTER (WHERE status IN ('completed', 'refunded', 'disputed')) AS gross,
       sum(refunded_amount) AS refunded,
       sum(amount) FILTER (WHERE status IN ('completed', 'refunded', 'disputed')) - sum(refunded_amount) AS net,
       sum(amount) FILTER (WHERE status = 'pending') AS open_pending
FROM p
GROUP BY ROLLUP (currency, provider)
HAVING GROUPING(currency) = 0  -- amounts of different currencies are never added up
ORDER BY 1, GROUPING(provider), 2;
