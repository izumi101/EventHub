-- name: duplicate_provider_ids
-- severity: CRITICAL
-- invariant: A provider checkout session or payment id identifies one payment:
--   legacy stripe_checkout_session_id / stripe_payment_intent_id, the new
--   (provider, provider_session_id) and (provider, provider_payment_id), and a
--   group booking's stripe_session_id / stripe_payment_intent_id are unique
--   when not empty.
-- why: The webhook and success page find the payment by these ids
--   (payments/services.py, bookings/payments.py). A duplicate confirms or
--   refunds the wrong ticket. Only (provider, provider_session_id) has a
--   unique index; the legacy columns have none.
SELECT stripe_checkout_session_id AS provider_id,
       'payments.stripe_checkout_session_id' AS id_column,
       count(*) AS row_count,
       string_agg(id::text, ', ' ORDER BY id) AS refs
FROM payments_payment
WHERE stripe_checkout_session_id <> ''
GROUP BY stripe_checkout_session_id
HAVING count(*) > 1
UNION ALL
SELECT stripe_payment_intent_id, 'payments.stripe_payment_intent_id',
       count(*), string_agg(id::text, ', ' ORDER BY id)
FROM payments_payment
WHERE stripe_payment_intent_id <> ''
GROUP BY stripe_payment_intent_id
HAVING count(*) > 1
UNION ALL
SELECT provider_session_id, 'payments.provider_session_id (' || provider || ')',
       count(*), string_agg(id::text, ', ' ORDER BY id)
FROM payments_payment
WHERE provider_session_id <> ''
GROUP BY provider, provider_session_id
HAVING count(*) > 1
UNION ALL
SELECT provider_payment_id, 'payments.provider_payment_id (' || provider || ')',
       count(*), string_agg(id::text, ', ' ORDER BY id)
FROM payments_payment
WHERE provider_payment_id <> ''
GROUP BY provider, provider_payment_id
HAVING count(*) > 1
UNION ALL
SELECT stripe_session_id, 'bookings.stripe_session_id',
       count(*), string_agg(id::text, ', ' ORDER BY id::text)
FROM bookings_booking
WHERE stripe_session_id <> ''
GROUP BY stripe_session_id
HAVING count(*) > 1
UNION ALL
SELECT stripe_payment_intent_id, 'bookings.stripe_payment_intent_id',
       count(*), string_agg(id::text, ', ' ORDER BY id::text)
FROM bookings_booking
WHERE stripe_payment_intent_id <> ''
GROUP BY stripe_payment_intent_id
HAVING count(*) > 1
ORDER BY 2, 1;
