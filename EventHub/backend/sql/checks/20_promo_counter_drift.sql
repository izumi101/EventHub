-- name: promo_counter_drift
-- severity: WARNING
-- invariant: promocode.times_used equals the number of live (pending or
--   confirmed) registrations that carry the code: a use is reserved at
--   registration and given back when the hold expires, the ticket is cancelled
--   or fully refunded (release_promo).
-- why: A counter above the real uses makes a code look exhausted too early
--   (lost sales); below lets it be used more often than max_uses.
SELECT pc.id AS promo_code_id,
       pc.event_id,
       pc.code,
       pc.times_used,
       count(r.id) AS live_uses
FROM events_promocode pc
LEFT JOIN events_registration r
       ON r.promo_code_id = pc.id AND r.status IN ('pending', 'confirmed')
GROUP BY pc.id, pc.event_id, pc.code, pc.times_used
HAVING pc.times_used <> count(r.id)
ORDER BY pc.id;
