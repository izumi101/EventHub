-- name: outbox_jobs_stuck
-- severity: WARNING
-- invariant: The job outbox drains: a pending job starts within 10 minutes of
--   its run_after, a running job finishes before its lease (run_after) is 10
--   minutes over, and no job has used up its attempts in the last 7 days.
-- why: Emails (sign-up codes, tickets), webhooks and search indexing run from
--   jobs_job. Old pending jobs mean the worker is down or too slow; failed
--   jobs are messages that were never delivered.
SELECT j.id AS job_id,
       j.kind,
       j.status,
       j.attempts,
       j.max_attempts,
       j.run_after,
       CASE
           WHEN j.status = 'pending' THEN 'pending for ' || date_trunc('minute', now() - j.run_after)
           WHEN j.status = 'running' THEN 'lease expired ' || date_trunc('minute', now() - j.run_after) || ' ago'
           ELSE 'failed after ' || j.attempts || ' attempts: ' || left(j.last_error, 120)
       END AS problem
FROM jobs_job j
WHERE (j.status = 'pending' AND j.run_after < now() - interval '10 minutes')
   OR (j.status = 'running' AND j.run_after < now() - interval '10 minutes')
   OR (j.status = 'failed' AND j.updated_at > now() - interval '7 days')
   OR (j.status IN ('pending', 'running') AND j.attempts >= j.max_attempts)
ORDER BY j.run_after, j.id;
