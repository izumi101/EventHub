-- Checkout funnel for paid tickets (read-only): how many checkouts end
-- paid, abandoned (hold expired), declined, or refunded.
SELECT upper(p.currency) AS currency,
       count(*) AS checkouts,
       count(*) FILTER (WHERE p.status IN ('completed', 'refunded', 'disputed')) AS paid,
       count(*) FILTER (WHERE p.status = 'pending') AS in_progress,
       count(*) FILTER (WHERE p.status = 'expired') AS abandoned,
       count(*) FILTER (WHERE p.status = 'failed') AS declined,
       round(100.0 * count(*) FILTER (WHERE p.status IN ('completed', 'refunded', 'disputed')) / count(*), 1)
           AS conversion_pct
FROM payments_payment p
WHERE p.registration_id IS NOT NULL
GROUP BY 1
ORDER BY 1;
