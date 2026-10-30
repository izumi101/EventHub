"""API views for the events app, split by concern.

``urls.py`` (and any external code) should keep importing from
``events.views`` — the submodule layout is an internal detail:

- ``events``          — categories, the Event ViewSet, my-events, recommendations
- ``registrations``   — ticket check-in by UUID, my-registrations
- ``engagement``      — favorites, reviews, notifications
- ``organizer``       — promo codes, questions, ticket types, staff,
                        webhooks, affiliates, refunds, waitlist overview
- ``checkin``         — named check-in lists and scan logs
- ``admin_dashboard`` — platform-wide admin stats
"""

from .admin_dashboard import AdminDashboardView
from .base import IsOrganizerOrReadOnly
from .checkin import (
    CheckInListAttendeesView,
    CheckInListCheckInView,
    CheckInListDetailView,
    EventCheckInListsView,
    EventCheckInLogsView,
)
from .engagement import (
    EventReviewsView,
    FavoritesListView,
    FavoriteToggleView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationsListView,
)
from .events import (
    CategoryListCreateView,
    EventViewSet,
    MyEventsView,
    RecommendationsView,
)
from .organizer import (
    AffiliateClickView,
    AffiliateDetailView,
    EventAffiliatesView,
    EventPromoCodesView,
    EventQuestionDetailView,
    EventQuestionsView,
    EventRefundRequestsView,
    EventStaffDetailView,
    EventStaffView,
    EventTicketTypesView,
    EventWaitlistView,
    EventWebhooksView,
    PromoCodeDetailView,
    ResolveRefundRequestView,
    TicketTypeDetailView,
    WebhookDetailView,
)
from .registrations import (
    MyRegistrationsView,
    RegistrationViewSet,
)

__all__ = [
    'AdminDashboardView',
    'AffiliateClickView',
    'AffiliateDetailView',
    'CategoryListCreateView',
    'CheckInListAttendeesView',
    'CheckInListCheckInView',
    'CheckInListDetailView',
    'EventAffiliatesView',
    'EventCheckInListsView',
    'EventCheckInLogsView',
    'EventPromoCodesView',
    'EventQuestionDetailView',
    'EventQuestionsView',
    'EventRefundRequestsView',
    'EventReviewsView',
    'EventStaffDetailView',
    'EventStaffView',
    'EventTicketTypesView',
    'EventViewSet',
    'EventWaitlistView',
    'EventWebhooksView',
    'FavoriteToggleView',
    'FavoritesListView',
    'IsOrganizerOrReadOnly',
    'MyEventsView',
    'MyRegistrationsView',
    'NotificationMarkAllReadView',
    'NotificationMarkReadView',
    'NotificationsListView',
    'PromoCodeDetailView',
    'RecommendationsView',
    'RegistrationViewSet',
    'ResolveRefundRequestView',
    'TicketTypeDetailView',
    'WebhookDetailView',
]
