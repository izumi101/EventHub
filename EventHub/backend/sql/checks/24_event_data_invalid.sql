-- name: event_data_invalid
-- severity: WARNING
-- invariant: An event ends after it starts, has a non-negative price, a
--   currency that is a three-letter ISO code, non-negative tax / fee
--   percentages, and a published event has at least one spot.
-- why: These columns feed pricing (events.billing), the listings and the
--   maintenance pass that completes past events. Bad values give negative
--   totals, events that never complete or a sold-out event nobody can buy.
SELECT event_id, title, problem
FROM (
    SELECT e.id AS event_id,
           e.title,
           CASE
               WHEN e.end_date IS NOT NULL AND e.end_date < e.date THEN 'ends before it starts'
               WHEN e.price < 0 THEN 'negative price'
               WHEN e.currency !~ '^[A-Za-z]{3}$' THEN 'currency is not an ISO code: ' || e.currency
               WHEN e.tax_percent < 0 OR e.service_fee_percent < 0 THEN 'negative tax or fee percentage'
               WHEN e.status = 'published' AND e.max_participants = 0 THEN 'published with no spots'
           END AS problem
    FROM events_event e
) checked
WHERE problem IS NOT NULL
ORDER BY event_id;
