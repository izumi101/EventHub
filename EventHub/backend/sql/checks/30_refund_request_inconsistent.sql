-- name: refund_request_inconsistent
-- severity: WARNING
-- invariant: An approved refund request has a payment with money refunded; a
--   resolved request (approved / rejected) has resolved_at; a pending request
--   belongs to a live ticket.
-- why: The organizer saw "approved" but the attendee got nothing back, or a
--   request waits for a decision on a ticket that no longer exists.
SELECT rr.id AS refund_request_id,
       rr.registration_id,
       rr.status,
       CASE
           WHEN rr.status = 'approved' AND COALESCE(p.refunded_amount, 0) = 0 THEN 'approved but nothing refunded'
           WHEN rr.status IN ('approved', 'rejected') AND rr.resolved_at IS NULL THEN 'resolved without resolved_at'
           ELSE 'pending request for a ' || r.status || ' ticket'
       END AS problem
FROM events_refundrequest rr
JOIN events_registration r ON r.id = rr.registration_id
LEFT JOIN payments_payment p ON p.registration_id = r.id
WHERE (rr.status = 'approved' AND COALESCE(p.refunded_amount, 0) = 0)
   OR (rr.status IN ('approved', 'rejected') AND rr.resolved_at IS NULL)
   OR (rr.status = 'pending' AND r.status NOT IN ('pending', 'confirmed'))
ORDER BY rr.id;
