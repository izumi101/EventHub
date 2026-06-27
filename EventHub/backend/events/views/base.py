"""Shared building blocks for the events views package."""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAuthenticated

from common.choices import EventStatusChoices
from common.permissions import can_manage_event

from ..models import Event


class IsOrganizerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.organizer == request.user


def event_queryset_for_user(user):
    queryset = Event.objects.select_related('organizer', 'category').prefetch_related('registrations')
    if user.is_authenticated and user.is_superuser:
        return queryset
    if user.is_authenticated:
        return queryset.filter(Q(organizer=user) | Q(status=EventStatusChoices.PUBLISHED))
    return queryset.filter(status=EventStatusChoices.PUBLISHED)


def restrict_status_list(queryset, user, status_value):
    if status_value == EventStatusChoices.PENDING:
        if user.is_authenticated and user.is_superuser:
            return queryset.filter(status=EventStatusChoices.PENDING)
        if user.is_authenticated:
            return queryset.filter(status=EventStatusChoices.PENDING, organizer=user)
        return queryset.none()

    if status_value == EventStatusChoices.PUBLISHED:
        return queryset.filter(status=EventStatusChoices.PUBLISHED)

    if user.is_authenticated and user.is_superuser:
        return queryset.filter(status=status_value)
    if user.is_authenticated:
        return queryset.filter(status=status_value, organizer=user)
    return queryset.filter(status=EventStatusChoices.PUBLISHED)


class ManagedEventListCreate(generics.ListCreateAPIView):
    """Base for event-scoped collections only managers may list+create."""
    permission_classes = [IsAuthenticated]
    model = None  # set in subclass

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            return self.model.objects.none()
        return self.model.objects.filter(event=event)

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self._event()
        return ctx


class ManagedDetail(generics.RetrieveUpdateDestroyAPIView):
    """Base for detail views restricted to the event's managers."""
    permission_classes = [IsAuthenticated]
    model = None

    def get_queryset(self):
        return self.model.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            raise PermissionDenied('You do not manage this event.')
