from django.contrib import admin
from .models import Booking, BookingSeat


class BookingSeatInline(admin.TabularInline):
    model = BookingSeat
    extra = 0
    readonly_fields = ('ticket_uuid',)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'owner', 'status', 'seat_count', 'total_price', 'created_at')
    list_filter = ('status',)
    search_fields = ('id', 'owner__username', 'event__title')
    inlines = [BookingSeatInline]


@admin.register(BookingSeat)
class BookingSeatAdmin(admin.ModelAdmin):
    list_display = ('booking', 'seat', 'price', 'attendee_name', 'is_checked_in')
    list_filter = ('is_checked_in',)
