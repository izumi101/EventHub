from django.urls import path

from . import views

urlpatterns = [
    path('', views.FeatureFlagsView.as_view(), name='feature_flags'),
]
