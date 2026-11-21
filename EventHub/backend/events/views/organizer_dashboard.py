"""The organizer dashboard API (docs/ORGANIZER_DASHBOARD.md): totals, a paged
event list with sales numbers, and a feed of recent activity."""

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from common.schema import FORBIDDEN, UNAUTHENTICATED, VALIDATION_ERROR

from .. import dashboard
from ..models import Event
from ..organizer_serializers import (
    ActivityFeedSerializer,
    ActivityQuerySerializer,
    DashboardSummarySerializer,
    OrganizerEventSerializer,
    OrganizerEventsQuerySerializer,
)

DASHBOARD_FORBIDDEN = OpenApiResponse(
    FORBIDDEN.response, description='The user neither is an organizer nor co-organizes an event.'
)


class CanUseOrganizerDashboard(BasePermission):
    message = 'The organizer dashboard is for organizers and event co-organizers.'

    def has_permission(self, request, view):
        return dashboard.can_use_dashboard(request.user)


class OrganizerEventsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


class OrganizerDashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, CanUseOrganizerDashboard]
    serializer_class = DashboardSummarySerializer
    pagination_class = None

    @extend_schema(
        responses={200: DashboardSummarySerializer, 401: UNAUTHENTICATED, 403: DASHBOARD_FORBIDDEN},
        description='Totals over all events the user organizes or co-organizes, independent of tabs and paging.',
    )
    def get(self, request):
        return Response(dashboard.dashboard_summary(request.user))


class OrganizerEventsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, CanUseOrganizerDashboard]
    serializer_class = OrganizerEventSerializer
    pagination_class = OrganizerEventsPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # OpenAPI generation, no real user
            return Event.objects.none()
        params = OrganizerEventsQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        tab = params.validated_data['tab']
        search = params.validated_data.get('search', '').strip()
        ordering = params.validated_data.get('ordering') or dashboard.DEFAULT_ORDERING[tab]

        queryset = dashboard.with_end(dashboard.managed_events(self.request.user))
        queryset = queryset.filter(dashboard.tab_filters(timezone.now())[tab])
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(location__icontains=search))
        queryset = dashboard.with_sales_annotations(queryset).select_related('organizer', 'category').with_capacity()
        return dashboard.order_events(queryset, ordering)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        serializer = self.get_serializer(
            page, many=True, context={**self.get_serializer_context(), 'stats': dashboard.bulk_event_stats(page)}
        )
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        parameters=[OrganizerEventsQuerySerializer],
        responses={
            # A list view: drf-spectacular wraps this in the paginator's page
            # (`PaginatedOrganizerEventList`), so declare the items only.
            200: OrganizerEventSerializer(many=True),
            400: VALIDATION_ERROR,
            401: UNAUTHENTICATED,
            403: DASHBOARD_FORBIDDEN,
        },
        description=(
            'Events the user organizes or co-organizes, one tab at a time, with sales numbers computed '
            'like `GET /events/{id}/analytics/` `kpis`. Every event is in exactly one tab.'
        ),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class OrganizerActivityView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, CanUseOrganizerDashboard]
    serializer_class = ActivityFeedSerializer
    pagination_class = None

    @extend_schema(
        parameters=[ActivityQuerySerializer],
        responses={
            200: ActivityFeedSerializer,
            400: VALIDATION_ERROR,
            401: UNAUTHENTICATED,
            403: DASHBOARD_FORBIDDEN,
        },
        description=(
            'Registrations, group bookings, check-ins and refunds of the last 30 days on managed events, newest first.'
        ),
    )
    def get(self, request):
        params = ActivityQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        feed = dashboard.activity_feed(
            request.user,
            limit=params.validated_data['limit'],
            cursor=params.validated_data.get('cursor'),
        )
        return Response(feed)
