-- name: duplicate_active_registrations
-- severity: CRITICAL
-- invariant: A user has at most one live (pending or confirmed) registration
--   per event. Cancelled / rejected rows are history and may repeat.
-- why: The partial unique index uniq_active_registration_per_user_event
--   enforces this today; the check guards against the index being dropped or
--   invalid (e.g. a failed concurrent rebuild) and documents the rule.
SELECT user_id,
       event_id,
       count(*) AS live_registrations,
       string_agg(id::text, ', ' ORDER BY id) AS registration_ids
FROM events_registration
WHERE status NOT IN ('cancelled', 'rejected')
GROUP BY user_id, event_id
HAVING count(*) > 1
ORDER BY user_id, event_id;
