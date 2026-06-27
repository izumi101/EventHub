"""Attendee engagement: favorites, reviews, notifications."""

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from ..models import Event, Favorite, Notification, Review
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
        return Favorite.objects.filter(user=self.request.user).select_related('event', 'event__organizer', 'event__category')


class FavoriteToggleView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        fav, created = Favorite.objects.get_or_create(user=request.user, event=event)
        if not created:
            fav.delete()
            return Response({'favorited': False})
        return Response({'favorited': True}, status=status.HTTP_201_CREATED)

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
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        if pk:
            Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'ok': True})
