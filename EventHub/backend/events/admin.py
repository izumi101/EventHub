from django.contrib import admin
from .models import (
    Category, Event, Registration, PromoCode, EventQuestion, WaitlistEntry,
    TicketType, EventStaff, Webhook, WebhookDelivery, Affiliate, RefundRequest,
)


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = ['registration', 'status', 'created_at', 'resolved_at']
    list_filter = ['status']


@admin.register(EventStaff)
class EventStaffAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'role', 'created_at']
    list_filter = ['role']


@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ['url', 'event', 'is_active', 'last_status', 'last_triggered_at']
    list_filter = ['is_active']


@admin.register(Affiliate)
class AffiliateAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'event', 'clicks', 'is_active']
    list_filter = ['is_active']


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'event', 'kind', 'price', 'quantity', 'is_active', 'order']
    list_filter = ['kind', 'is_active']
    search_fields = ['name', 'event__title']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'event', 'discount_type', 'discount_value', 'times_used', 'max_uses', 'is_active', 'expires_at']
    list_filter = ['discount_type', 'is_active']
    search_fields = ['code', 'event__title']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'organizer', 'category', 'date', 'price', 'status']
    list_filter = ['status', 'category', 'is_online']
    search_fields = ['title', 'description']
    date_hierarchy = 'date'


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'status', 'registered_at']
    list_filter = ['status']


@admin.register(EventQuestion)
class EventQuestionAdmin(admin.ModelAdmin):
    list_display = ['label', 'event', 'question_type', 'is_required', 'order']
    list_filter = ['question_type', 'is_required']


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'status', 'created_at', 'offer_expires_at']
    list_filter = ['status']
