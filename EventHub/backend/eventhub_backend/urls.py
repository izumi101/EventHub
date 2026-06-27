from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """Health check endpoint for monitoring and container probes."""
    try:
        connection.ensure_connection()
        return JsonResponse({'status': 'ok', 'db': 'connected'})
    except Exception:
        return JsonResponse({'status': 'error', 'db': 'disconnected'}, status=503)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('events.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/bookings/', include('bookings.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

