-- name: currency_mismatch
-- severity: CRITICAL
-- invariant: A payment is in its event's currency, and a refund in its
--   payment's currency. Compared case-insensitively: payments store the code
--   lower case ('kzt'), events and refunds upper case ('KZT') until the
--   provider switch normalises it (payments/0005 docstring).
-- why: An amount without the right currency is a different amount: 15 000
--   KZT charged as 15 000 USD. Refund and revenue totals per currency would
--   mix money.
SELECT 'payment:' || p.id AS ref,
       upper(p.currency) AS currency,
       upper(e.currency) AS expected_currency,
       'payment vs event ' || e.id AS problem
FROM payments_payment p
JOIN events_registration r ON r.id = p.registration_id
JOIN events_event e ON e.id = r.event_id
WHERE upper(p.currency) <> upper(e.currency)
UNION ALL
SELECT 'payment:' || p.id,
       upper(p.currency),
       upper(e.currency),
       'booking payment vs event ' || e.id
FROM payments_payment p
JOIN bookings_booking b ON b.id = p.booking_id
JOIN events_event e ON e.id = b.event_id
WHERE upper(p.currency) <> upper(e.currency)
UNION ALL
SELECT 'refund:' || rf.id,
       upper(rf.currency),
       upper(p.currency),
       'refund vs payment ' || p.id
FROM payments_refund rf
JOIN payments_payment p ON p.id = rf.payment_id
WHERE upper(rf.currency) <> upper(p.currency)
ORDER BY 1;
