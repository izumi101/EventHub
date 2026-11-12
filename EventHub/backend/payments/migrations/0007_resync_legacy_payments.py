"""Re-run the legacy copy right before the code switches to the new columns.

Why: `payments/0005` copied the `stripe_*` columns of `Payment` and the money
fields of `Booking` into the provider-neutral ledger when WP1a was deployed.
The release that followed still ran the legacy services, which kept writing
only the old columns. Rows they created or changed after 0005 ran (a new
checkout, a payment intent stored by a webhook, a group booking paid or
refunded) are missing from the ledger or stale there. The release that ships
this migration reads only the new columns, so it must start from an up to
date copy.

What it does:

1. `copy_legacy_payments` from 0005 again. It is idempotent: rows written by
   the provider-neutral code carry no `legacy_import` marker and are kept;
   ticket payments without a provider get one; booking payments are
   re-derived from their booking.
2. A refresh pass for ticket payments that 0005 imported and the legacy code
   then moved on: a newer Checkout Session (the buyer reopened checkout) or a
   payment intent that differs from the copied one. 0005 only fills empty
   columns, so without this pass the ledger would keep pointing at the old
   session and the success page / webhook of the newer one would not find
   the payment. Moved ids are recorded in the marker note.

Reverse is a no-op: the copied values are harmless to the previous release,
which does not read them, and reversing 0005 removes the copied booking rows.

The legacy columns stay until the contract step (WP1c). That migration must
run this resync once more before it drops them, for the rows the previous
release wrote while this one was being rolled out.
"""

from importlib import import_module

from django.db import migrations

copy_0005 = import_module('payments.migrations.0005_copy_legacy_payments')

MIGRATION = '0007_resync_legacy_payments'
MARKER = copy_0005.MARKER


def refresh_moved_ticket_ids(Payment, counters):
    imported = Payment.objects.filter(
        registration__isnull=False,
        provider__in=['stripe', 'mock'],
        provider_payload__has_key=MARKER,
    ).order_by('pk')
    for payment in imported.iterator():
        session, intent = payment.stripe_checkout_session_id, payment.stripe_payment_intent_id
        payload = dict(payment.provider_payload or {})
        note = dict(payload.get(MARKER) or {})
        updates = {}
        if session and session != payment.provider_session_id:
            if copy_0005._session_id_is_free(Payment, payment.provider, session, payment.pk):
                if payment.provider_session_id:
                    note.setdefault('previous_session_ids', []).append(payment.provider_session_id)
                updates['provider_session_id'] = session
                updates['attempt'] = max(payment.attempt, 1) + (1 if payment.provider_session_id else 0)
            else:
                note['session_id_conflict'] = session
        if intent and intent != payment.provider_payment_id:
            if payment.provider_payment_id:
                note['previous_payment_id'] = payment.provider_payment_id
            updates['provider_payment_id'] = intent
        if updates or note != payload.get(MARKER):
            note['resynced_by'] = MIGRATION
            payload[MARKER] = note
            updates['provider_payload'] = payload
            # QuerySet.update(): keeps `updated_at` (the last real change).
            Payment.objects.filter(pk=payment.pk).update(**updates)
            counters['ticket_payments_refreshed'] += 1


def resync_legacy_payments(apps, schema_editor=None):
    counters = copy_0005.copy_legacy_payments(apps, schema_editor)
    counters['ticket_payments_refreshed'] = 0
    refresh_moved_ticket_ids(apps.get_model('payments', 'Payment'), counters)
    return counters


class Migration(migrations.Migration):
    dependencies = [
        ('bookings', '0003_booking_refunds'),
        ('payments', '0006_payment_status_choices'),
    ]

    operations = [
        migrations.RunPython(resync_legacy_payments, migrations.RunPython.noop, elidable=False),
    ]
