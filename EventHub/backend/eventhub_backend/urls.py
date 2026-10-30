from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView


def health_check(request):
    """Health check endpoint for monitoring and container probes."""
    try:
        connection.ensure_connection()
        return JsonResponse({'status': 'ok', 'db': 'connected'})
    except Exception:
        return JsonResponse({'status': 'error', 'db': 'disconnected'}, status=503)


api_patterns = [
    path('auth/', include('accounts.urls')),
    path('', include('events.urls')),
    path('payments/', include('payments.urls')),
    path('bookings/', include('bookings.urls')),
    path('feature-flags/', include('featureflags.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Split view: Swagger's config comes from a script URL, not an inline
    # <script>, so the page works under the strict CSP.
    path('api/v1/docs/', SpectacularSwaggerSplitView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/', include(api_patterns)),
    # Deprecated unversioned alias of v1 (see common.api_versioning). Its own
    # namespace keeps reverse() pointing at /api/v1/.
    path('api/', include((api_patterns, 'legacy'), namespace='legacy')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
