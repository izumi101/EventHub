-- name: past_event_still_published
-- severity: WARNING
-- invariant: An event whose end (end_date, or date when end_date is empty)
--   passed more than an hour ago is no longer 'published'; the maintenance
--   pass marks it 'completed' every minute.
-- why: A past event that stays published still appears in listings and
--   search. It is the most visible symptom of a stopped worker.
SELECT e.id AS event_id,
       e.title,
       e.date,
       e.end_date,
       e.status
FROM events_event e
WHERE e.status = 'published'
  AND COALESCE(e.end_date, e.date) < now() - interval '1 hour'
ORDER BY COALESCE(e.end_date, e.date), e.id;
