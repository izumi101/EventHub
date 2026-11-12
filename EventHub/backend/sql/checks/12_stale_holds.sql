-- name: stale_holds
-- severity: WARNING
-- invariant: Unpaid holds end: a pending registration has seat_held_until and
--   is released (cancelled) at most a few minutes after it passes; a holding
--   group booking is expired the same way. Grace: 15 minutes (holds last 10,
--   the worker runs the maintenance pass every minute).
-- why: A hold that outlives its deadline keeps a spot or a seat off sale.
--   Rows here mean the maintenance job (run_worker -> run_maintenance) is not
--   running, or a code path created a pending registration without a hold
--   deadline, which nothing ever releases.
SELECT 'registration:' || r.id AS ref,
       r.event_id,
       r.seat_held_until AS hold_until,
       CASE
           WHEN r.seat_held_until IS NULL THEN 'pending registration without hold deadline (never released)'
           ELSE 'hold expired ' || date_trunc('minute', now() - r.seat_held_until) || ' ago'
       END AS problem
FROM events_registration r
LEFT JOIN payments_payment p ON p.registration_id = r.id
WHERE r.status = 'pending'
  AND (r.seat_held_until IS NULL OR r.seat_held_until < now() - interval '15 minutes')
  AND COALESCE(p.status, '') <> 'completed'
UNION ALL
SELECT 'booking:' || b.id,
       b.event_id,
       b.hold_expires_at,
       CASE
           WHEN b.hold_expires_at IS NULL THEN 'holding booking without hold deadline (never released)'
           ELSE 'hold expired ' || date_trunc('minute', now() - b.hold_expires_at) || ' ago'
       END
FROM bookings_booking b
WHERE b.status = 'holding'
  AND (b.hold_expires_at IS NULL OR b.hold_expires_at < now() - interval '15 minutes')
ORDER BY 1;
