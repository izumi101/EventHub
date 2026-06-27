from django.urls import path
from . import views

urlpatterns = [
    path('create-checkout/<int:registration_id>/', views.CreateCheckoutSessionView.as_view(), name='create-checkout'),
    path('webhook/', views.StripeWebhookView.as_view(), name='stripe-webhook'),
    path('verify/', views.VerifyPaymentView.as_view(), name='verify-payment'),
    path('refund/<int:registration_id>/', views.RefundPaymentView.as_view(), name='refund-payment'),
    path('mark-offline/<int:registration_id>/', views.MarkOfflinePaidView.as_view(), name='mark-offline-paid'),
    path('invoice/<int:registration_id>/', views.InvoiceView.as_view(), name='invoice'),
]
