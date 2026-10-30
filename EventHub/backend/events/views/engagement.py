"""Attendee engagement: favorites, reviews, notifications."""

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from common.schema import NOT_FOUND, UNAUTHENTICATED

from .. import schema as api
from ..models import Event, Favorite, Notification, Review
from .base import event_queryset_for_user
from ..serializers import (
    FavoriteSerializer,
    NotificationSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
)


class FavoritesListView(generics.ListAPIView):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Favorite.objects.filter(user=self.request.user)
            .prefetch_related(
                Prefetch('event', queryset=Event.objects.select_related('organizer', 'category').with_capacity()),
            )
        )


class FavoriteToggleView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: api.FavoriteStateSerializer, 201: api.FavoriteStateSerializer, 401: UNAUTHENTICATED, 404: NOT_FOUND})
    def post(self, request, event_id):
        # Only events the user may see (no favouriting someone else's draft).
        event = get_object_or_404(event_queryset_for_user(request.user), pk=event_id)
        fav, created = Favorite.objects.get_or_create(user=request.user, event=event)
        if not created:
            fav.delete()
            return Response({'favorited': False})
        return Response({'favorited': True}, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: api.FavoriteStateSerializer, 401: UNAUTHENTICATED})
    def get(self, request, event_id):
        exists = Favorite.objects.filter(user=request.user, event_id=event_id).exists()
        return Response({'favorited': exists})


class EventReviewsView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(event_id=self.kwargs['event_id']).select_related('user', 'user__profile')

    def perform_create(self, serializer):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        serializer.save(user=self.request.user, event=event)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event_id'] = self.kwargs['event_id']
        return ctx


class NotificationsListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)[:50]


class NotificationMarkReadView(generics.GenericAPIView):
    """Mark one notification (by id) — or, via the subclass below, all — as read."""
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id='notification_mark_read', request=None,
                   responses={200: api.OkSerializer, 401: UNAUTHENTICATED})
    def post(self, request, pk=None):
        if pk:
            Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'ok': True})


class NotificationMarkAllReadView(NotificationMarkReadView):
    @extend_schema(operation_id='notifications_mark_all_read', request=None,
                   responses={200: api.OkSerializer, 401: UNAUTHENTICATED})
    def post(self, request, pk=None):
        return super().post(request)
