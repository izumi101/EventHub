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

from .base import IsOrganizerOrReadOnly
from .events import (
    CategoryListCreateView,
    EventViewSet,
    MyEventsView,
    RecommendationsView,
)
from .registrations import (
    MyRegistrationsView,
    RegistrationViewSet,
)
from .engagement import (
    EventReviewsView,
    FavoritesListView,
    FavoriteToggleView,
    NotificationMarkReadView,
    NotificationsListView,
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
from .checkin import (
    CheckInListAttendeesView,
    CheckInListCheckInView,
    CheckInListDetailView,
    EventCheckInListsView,
    EventCheckInLogsView,
)
from .admin_dashboard import AdminDashboardView

__all__ = [
    'IsOrganizerOrReadOnly',
    'CategoryListCreateView',
    'EventViewSet',
    'MyEventsView',
    'RecommendationsView',
    'MyRegistrationsView',
    'RegistrationViewSet',
    'EventReviewsView',
    'FavoritesListView',
    'FavoriteToggleView',
    'NotificationMarkReadView',
    'NotificationsListView',
    'AffiliateClickView',
    'AffiliateDetailView',
    'EventAffiliatesView',
    'EventPromoCodesView',
    'EventQuestionDetailView',
    'EventQuestionsView',
    'EventRefundRequestsView',
    'EventStaffDetailView',
    'EventStaffView',
    'EventTicketTypesView',
    'EventWaitlistView',
    'EventWebhooksView',
    'PromoCodeDetailView',
    'ResolveRefundRequestView',
    'TicketTypeDetailView',
    'WebhookDetailView',
    'CheckInListAttendeesView',
    'CheckInListCheckInView',
    'CheckInListDetailView',
    'EventCheckInListsView',
    'EventCheckInLogsView',
    'AdminDashboardView',
]
