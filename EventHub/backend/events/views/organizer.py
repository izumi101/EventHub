"""Organizer tooling: promo codes, questions, ticket types, staff,
webhooks, affiliates, refund requests, waitlist overview."""

from django.db import models
from django.db.models import Case, IntegerField, When
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from common.permissions import can_manage_event

from ..models import (
    Affiliate,
    Event,
    EventQuestion,
    EventStaff,
    PromoCode,
    RefundRequest,
    TicketType,
    WaitlistEntry,
    Webhook,
)
from ..serializers import (
    AffiliateSerializer,
    EventQuestionSerializer,
    EventStaffSerializer,
    PromoCodeSerializer,
    RefundRequestSerializer,
    TicketTypeSerializer,
    WaitlistEntrySerializer,
    WebhookSerializer,
)
from ..services import resolve_refund_request
from .base import ManagedDetail, ManagedEventListCreate


class EventPromoCodesView(generics.ListCreateAPIView):
    """List + create promo codes for an event the user manages."""
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAuthenticated]

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            return PromoCode.objects.none()
        return event.promo_codes.all()

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)


class PromoCodeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PromoCode.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            raise PermissionDenied('You do not manage this event.')


class EventQuestionsView(generics.ListCreateAPIView):
    """List + create custom checkout questions for an event you manage.

    GET is public (the checkout form needs them); POST requires management.
    """
    serializer_class = EventQuestionSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        return EventQuestion.objects.filter(event_id=self.kwargs['event_id'])

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)


class EventQuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EventQuestionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EventQuestion.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            raise PermissionDenied('You do not manage this event.')


class EventTicketTypesView(generics.ListCreateAPIView):
    """List + create ticket tiers for an event.

    GET is public (the buy box needs them); POST requires management.
    """
    serializer_class = TicketTypeSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        return TicketType.objects.filter(event_id=self.kwargs['event_id'])

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)


class TicketTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TicketTypeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TicketType.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            raise PermissionDenied('You do not manage this event.')


# ── Event staff ──
class EventStaffView(ManagedEventListCreate):
    model = EventStaff
    serializer_class = EventStaffSerializer

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            raise PermissionDenied('You do not manage this event.')
        serializer.save()  # create() reads event from context


class EventStaffDetailView(ManagedDetail):
    model = EventStaff
    serializer_class = EventStaffSerializer


# ── Webhooks ──
class EventWebhooksView(ManagedEventListCreate):
    model = Webhook
    serializer_class = WebhookSerializer


class WebhookDetailView(ManagedDetail):
    model = Webhook
    serializer_class = WebhookSerializer


# ── Affiliates ──
class EventAffiliatesView(ManagedEventListCreate):
    model = Affiliate
    serializer_class = AffiliateSerializer


class AffiliateDetailView(ManagedDetail):
    model = Affiliate
    serializer_class = AffiliateSerializer


class AffiliateClickView(generics.GenericAPIView):
    """Public: record a click when someone opens an event via ?ref=CODE."""
    permission_classes = [AllowAny]

    def post(self, request, event_id):
        code = (request.data.get('code') or '').strip()
        if code:
            Affiliate.objects.filter(
                event_id=event_id, code__iexact=code, is_active=True,
            ).update(clicks=models.F('clicks') + 1)
        return Response({'ok': True})


class EventRefundRequestsView(generics.ListAPIView):
    """Organizer lists refund requests for their event (pending first)."""
    serializer_class = RefundRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            return RefundRequest.objects.none()
        qs = RefundRequest.objects.filter(
            registration__event=event,
        ).select_related('registration__user', 'registration__payment', 'registration__ticket_type')
        # Pending first, then most recent.
        return qs.annotate(
            _order=Case(When(status='pending', then=0), default=1, output_field=IntegerField()),
        ).order_by('_order', '-created_at')


class ResolveRefundRequestView(generics.GenericAPIView):
    """Organizer approves or rejects a refund request."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        rr = get_object_or_404(RefundRequest.objects.select_related('registration__event', 'registration__user'), pk=pk)
        approve = bool(request.data.get('approve'))
        try:
            resolve_refund_request(
                refund_request=rr, actor=request.user, approve=approve,
                note=request.data.get('note', ''),
            )
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': rr.status})


class EventWaitlistView(generics.ListAPIView):
    """Organizer views everyone on the waitlist for their event."""
    serializer_class = WaitlistEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            return WaitlistEntry.objects.none()
        return WaitlistEntry.objects.filter(event=event).select_related('user')
