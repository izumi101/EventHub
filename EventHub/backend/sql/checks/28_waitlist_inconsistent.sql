-- name: waitlist_inconsistent
-- severity: WARNING
-- invariant: An offered waitlist entry has an offer deadline and is expired
--   (passed to the next person) within 15 minutes after it; a person who
--   already holds a live ticket is not still waiting or offered (their entry
--   is marked converted at registration).
-- why: A stale offer reserves a spot nobody can buy (register_for_event keeps
--   offered spots for the offered users); a waiting entry of a ticket holder
--   gets them a second offer and pushes others down the queue.
SELECT w.id AS waitlist_entry_id,
       w.event_id,
       w.user_id,
       w.status,
       CASE
           WHEN w.status = 'offered' AND w.offer_expires_at IS NULL THEN 'offer without deadline'
           WHEN w.status = 'offered' AND w.offer_expires_at < now() - interval '15 minutes'
               THEN 'offer expired ' || date_trunc('minute', now() - w.offer_expires_at) || ' ago'
           ELSE 'still ' || w.status || ' but already has a live ticket'
       END AS problem
FROM events_waitlistentry w
WHERE (w.status = 'offered' AND (w.offer_expires_at IS NULL OR w.offer_expires_at < now() - interval '15 minutes'))
   OR (w.status IN ('waiting', 'offered') AND EXISTS (
          SELECT 1 FROM events_registration r
          WHERE r.user_id = w.user_id AND r.event_id = w.event_id AND r.status IN ('pending', 'confirmed')))
ORDER BY w.id;
