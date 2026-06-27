from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'events', views.EventViewSet, basename='event')
router.register(r'registrations', views.RegistrationViewSet, basename='registration')

urlpatterns = [
    path('', include(router.urls)),
    path('categories/', views.CategoryListCreateView.as_view(), name='category-list'),
    path('my-events/', views.MyEventsView.as_view(), name='my-events'),
    path('my-registrations/', views.MyRegistrationsView.as_view(), name='my-registrations'),
    path('recommendations/', views.RecommendationsView.as_view(), name='recommendations'),
    # Favorites
    path('favorites/', views.FavoritesListView.as_view(), name='favorites-list'),
    path('favorites/<int:event_id>/', views.FavoriteToggleView.as_view(), name='favorite-toggle'),
    # Reviews
    path('events/<int:event_id>/reviews/', views.EventReviewsView.as_view(), name='event-reviews'),
    # Notifications
    path('notifications/', views.NotificationsListView.as_view(), name='notifications-list'),
    path('notifications/read/', views.NotificationMarkReadView.as_view(), name='notifications-read-all'),
    path('notifications/<int:pk>/read/', views.NotificationMarkReadView.as_view(), name='notification-read'),
    # Promo codes (organizer)
    path('events/<int:event_id>/promo-codes/', views.EventPromoCodesView.as_view(), name='event-promo-codes'),
    path('promo-codes/<int:pk>/', views.PromoCodeDetailView.as_view(), name='promo-code-detail'),
    # Ticket types
    path('events/<int:event_id>/ticket-types/', views.EventTicketTypesView.as_view(), name='event-ticket-types'),
    path('ticket-types/<int:pk>/', views.TicketTypeDetailView.as_view(), name='ticket-type-detail'),
    # Custom questions
    path('events/<int:event_id>/questions/', views.EventQuestionsView.as_view(), name='event-questions'),
    path('questions/<int:pk>/', views.EventQuestionDetailView.as_view(), name='question-detail'),
    # Waitlist (organizer view)
    path('events/<int:event_id>/waitlist-entries/', views.EventWaitlistView.as_view(), name='event-waitlist'),
    # Refund requests
    path('events/<int:event_id>/refund-requests/', views.EventRefundRequestsView.as_view(), name='event-refund-requests'),
    path('refund-requests/<int:pk>/resolve/', views.ResolveRefundRequestView.as_view(), name='resolve-refund-request'),
    # Team / roles
    path('events/<int:event_id>/staff/', views.EventStaffView.as_view(), name='event-staff'),
    path('staff/<int:pk>/', views.EventStaffDetailView.as_view(), name='staff-detail'),
    # Webhooks
    path('events/<int:event_id>/webhooks/', views.EventWebhooksView.as_view(), name='event-webhooks'),
    path('webhooks/<int:pk>/', views.WebhookDetailView.as_view(), name='webhook-detail'),
    # Affiliates
    path('events/<int:event_id>/affiliates/', views.EventAffiliatesView.as_view(), name='event-affiliates'),
    path('affiliates/<int:pk>/', views.AffiliateDetailView.as_view(), name='affiliate-detail'),
    path('events/<int:event_id>/affiliate-click/', views.AffiliateClickView.as_view(), name='affiliate-click'),
    # Admin dashboard
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    # Check-in lists & logs
    path('events/<int:event_id>/checkin-lists/', views.EventCheckInListsView.as_view(), name='event-checkin-lists'),
    path('checkin-lists/<int:pk>/', views.CheckInListDetailView.as_view(), name='checkin-list-detail'),
    path('checkin-lists/<int:pk>/attendees/', views.CheckInListAttendeesView.as_view(), name='checkin-list-attendees'),
    path('checkin-lists/<int:pk>/check-in/', views.CheckInListCheckInView.as_view(), name='checkin-list-checkin'),
    path('events/<int:event_id>/checkin-logs/', views.EventCheckInLogsView.as_view(), name='event-checkin-logs'),
]
