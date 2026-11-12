-- name: checkin_log_wrong_event
-- severity: CRITICAL
-- invariant: Every check-in log entry joins a registration and a check-in list
--   (gate) of the same event.
-- why: The scanner looks the ticket up within the gate's event
--   (views/checkin.py). A log entry across events means a ticket for one event
--   was accepted at another event's door.
SELECT l.id AS checkin_log_id,
       l.registration_id,
       r.event_id AS ticket_event_id,
       cl.event_id AS gate_event_id,
       l.action,
       l.created_at
FROM events_checkinlog l
JOIN events_checkinlist cl ON cl.id = l.checkin_list_id
JOIN events_registration r ON r.id = l.registration_id
WHERE r.event_id <> cl.event_id
ORDER BY l.id;
