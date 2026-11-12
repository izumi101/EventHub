-- name: promo_over_max_uses
-- severity: CRITICAL
-- invariant: A promo code with max_uses is used at most max_uses times: both
--   its counter (times_used) and the number of live registrations carrying it.
-- why: reserve_promo takes a use with a conditional UPDATE so two buyers
--   cannot both take the last one. More uses than allowed is a discount the
--   organizer did not grant.
SELECT pc.id AS promo_code_id,
       pc.event_id,
       pc.code,
       pc.max_uses,
       pc.times_used,
       count(r.id) AS live_uses
FROM events_promocode pc
LEFT JOIN events_registration r
       ON r.promo_code_id = pc.id AND r.status IN ('pending', 'confirmed')
WHERE pc.max_uses IS NOT NULL
GROUP BY pc.id, pc.event_id, pc.code, pc.max_uses, pc.times_used
HAVING pc.times_used > pc.max_uses OR count(r.id) > pc.max_uses
ORDER BY pc.id;
