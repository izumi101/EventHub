from django.urls import path

from . import views

# Mounted at auth/profile/notifications/ (next to auth/profile/).
urlpatterns = [
    path('', views.NotificationPreferencesView.as_view(), name='notification_preferences'),
]
