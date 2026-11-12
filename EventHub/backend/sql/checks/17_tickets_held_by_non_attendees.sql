-- name: tickets_held_by_non_attendees
-- severity: WARNING
-- invariant: Live tickets belong to attendee accounts: not to staff or
--   superusers and not to accounts whose profile role is organizer
--   (ensure_attendee_can_buy).
-- why: The purchase paths refuse these accounts. A row is either a rule
--   bypass or an account whose role changed after it bought (then it is
--   expected and can be ignored after review).
SELECT 'registration:' || r.id AS ref,
       r.event_id,
       u.id AS user_id,
       CASE
           WHEN u.is_superuser THEN 'superuser'
           WHEN u.is_staff THEN 'staff'
           ELSE 'organizer role'
       END AS account_type
FROM events_registration r
JOIN auth_user u ON u.id = r.user_id
LEFT JOIN accounts_userprofile up ON up.user_id = u.id
WHERE r.status IN ('pending', 'confirmed')
  AND (u.is_staff OR u.is_superuser OR up.role = 'organizer')
UNION ALL
SELECT 'booking:' || b.id,
       b.event_id,
       u.id,
       CASE
           WHEN u.is_superuser THEN 'superuser'
           WHEN u.is_staff THEN 'staff'
           ELSE 'organizer role'
       END
FROM bookings_booking b
JOIN auth_user u ON u.id = b.owner_id
LEFT JOIN accounts_userprofile up ON up.user_id = u.id
WHERE b.status IN ('holding', 'confirmed')
  AND (u.is_staff OR u.is_superuser OR up.role = 'organizer')
ORDER BY 1;
