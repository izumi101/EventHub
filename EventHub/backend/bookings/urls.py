from django.urls import path
from . import views

urlpatterns = [
    path('', views.BookingCreateView.as_view(), name='booking-create'),
    path('mine/', views.MyBookingsView.as_view(), name='booking-mine'),
    path('verify/', views.VerifyBookingView.as_view(), name='booking-verify'),
    path('<uuid:pk>/', views.BookingDetailView.as_view(), name='booking-detail'),
    path('<uuid:pk>/checkout/', views.BookingCheckoutView.as_view(), name='booking-checkout'),
    path('<uuid:pk>/cancel/', views.BookingCancelView.as_view(), name='booking-cancel'),
    path('shared/<uuid:token>/', views.SharedBookingView.as_view(), name='booking-shared'),
    path('shared/<uuid:token>/claim/', views.ClaimSeatView.as_view(), name='booking-claim'),
]
