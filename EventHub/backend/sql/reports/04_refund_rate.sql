-- Refund rate per category (read-only). Paid tickets = payments that took
-- money; refund rate = share of them refunded fully or partly; refunded
-- share = refunded money / gross. Cancelled events refund everything and are
-- shown separately so they do not hide the normal rate.
SELECT COALESCE(c.name, '(no category)') AS category,
       (e.status = 'cancelled') AS event_cancelled,
       count(*) AS paid_tickets,
       count(*) FILTER (WHERE p.status = 'refunded') AS refunded_full,
       count(*) FILTER (WHERE p.status = 'completed' AND p.refunded_amount > 0) AS refunded_partly,
       round(100.0 * count(*) FILTER (WHERE p.refunded_amount > 0) / count(*), 1) AS refund_rate_pct,
       round(100.0 * sum(p.refunded_amount) / NULLIF(sum(p.amount), 0), 1) AS refunded_money_pct
FROM payments_payment p
JOIN events_registration r ON r.id = p.registration_id
JOIN events_event e ON e.id = r.event_id
LEFT JOIN events_category c ON c.id = e.category_id
WHERE p.status IN ('completed', 'refunded', 'disputed')
GROUP BY 1, 2
ORDER BY 2, refund_rate_pct DESC;
