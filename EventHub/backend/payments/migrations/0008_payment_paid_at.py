"""`Payment.paid_at`: when the money first arrived.

`created_at` is the start of checkout and `updated_at` moves on every refund,
so neither says on which day an organizer earned a payment (an offline payment
is marked paid days after it was created; a checkout can span midnight). The
column is stamped once by `payments.state.mark_paid` when a payment first
becomes completed (or refunded / disputed).

Expand step only: add the column and its index, then backfill the existing
paid rows. No CHECK yet: a code-only rollback to the previous release must
keep working, and that code completes payments without `paid_at`. Readers
therefore fall back to `created_at` for a paid row without it. The CHECK
(`payment_paid_at_when_paid`) is the contract step of a later release.

Backfill, per payment that is completed, refunded or disputed: the time of the
earliest processed "paid" provider callback (`PaymentEvent.processed_at`, else
`received_at`) when there is one, else `created_at` (legacy rows and offline
or mock payments have no callback; their checkout start is the best record).

Reverse: the index and the column are dropped by the schema operations; the
data step has nothing to undo.
"""

from django.db import migrations, models
from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import Coalesce

PAID_STATUSES = ['completed', 'refunded', 'disputed']


def backfill_paid_at(apps, schema_editor=None):
    """Fill `paid_at` of paid payments that lack it; returns how many rows."""
    Payment = apps.get_model('payments', 'Payment')
    PaymentEvent = apps.get_model('payments', 'PaymentEvent')
    first_paid_callback = (
        PaymentEvent.objects.filter(payment=OuterRef('pk'), kind='paid', outcome='processed')
        .annotate(arrived=Coalesce('processed_at', 'received_at'))
        .order_by('arrived', 'pk')
        .values('arrived')[:1]
    )
    # QuerySet.update(): keeps `updated_at` (the last real change).
    return Payment.objects.filter(status__in=PAID_STATUSES, paid_at__isnull=True).update(
        paid_at=Coalesce(Subquery(first_paid_callback), F('created_at'))
    )


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0007_resync_legacy_payments'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='paid_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['paid_at'], name='payment_paid_at_idx'),
        ),
        migrations.RunPython(backfill_paid_at, migrations.RunPython.noop, elidable=False),
    ]
