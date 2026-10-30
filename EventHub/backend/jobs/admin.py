from django.contrib import admin
from django.utils import timezone

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['id', 'kind', 'status', 'attempts', 'max_attempts', 'run_after', 'created_at']
    list_filter = ['status', 'kind']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['retry']

    @admin.action(description='Retry selected jobs now')
    def retry(self, request, queryset):
        updated = queryset.exclude(status=Job.STATUS_DONE).update(
            status=Job.STATUS_PENDING,
            run_after=timezone.now(),
            attempts=0,
        )
        self.message_user(request, f'{updated} job(s) queued again.')
