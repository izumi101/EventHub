from django.contrib import admin

from .models import Payment, PaymentEvent, Refund

# Money moves only through the payment services (and the provider), so the
# admin shows these records but never edits amounts, provider ids or state.
PAYMENT_READ_ONLY = (
    'registration',
    'booking',
    'amount',
    'currency',
    'status',
    'method',
    'refunded_amount',
    'refunded_at',
    'provider',
    'provider_session_id',
    'provider_payment_id',
    'provider_payload',
    'attempt',
    'stripe_payment_intent_id',
    'stripe_checkout_session_id',
    'created_at',
    'updated_at',
)


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    can_delete = False
    fields = ('created_at', 'kind', 'amount', 'currency', 'status', 'provider_refund_id', 'processed_at')
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'registration', 'booking', 'provider', 'amount', 'currency', 'status', 'created_at']
    list_filter = ['status', 'provider', 'method']
    search_fields = [
        'provider_session_id',
        'provider_payment_id',
        'stripe_checkout_session_id',
        'stripe_payment_intent_id',
    ]
    readonly_fields = PAYMENT_READ_ONLY
    inlines = [RefundInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ['id', 'payment', 'kind', 'amount', 'currency', 'status', 'created_at', 'processed_at']
    list_filter = ['status', 'kind', 'provider']
    search_fields = ['idempotency_key', 'provider_refund_id', 'provider_payment_id']
    readonly_fields = (
        'id',
        'payment',
        'amount',
        'currency',
        'kind',
        'status',
        'requested_by',
        'provider',
        'provider_payment_id',
        'provider_refund_id',
        'idempotency_key',
        'error',
        'attempts',
        'created_at',
        'processed_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ['received_at', 'provider', 'kind', 'event_id', 'payment', 'outcome']
    list_filter = ['provider', 'kind', 'outcome']
    search_fields = ['event_id']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
