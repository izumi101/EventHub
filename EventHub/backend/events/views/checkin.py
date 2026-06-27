"""Check-in lists: per-list attendee state, scanning, audit logs."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.choices import RegistrationStatusChoices
from common.permissions import can_manage_event

from ..models import CheckInList, CheckInLog, Event, Registration
from ..serializers import CheckInListSerializer, CheckInLogSerializer


class EventCheckInListsView(generics.ListCreateAPIView):
    """GET list / POST create check-in lists for an event (organizer only)."""
    serializer_class = CheckInListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # lists are few; frontend expects a bare array

    def _get_event(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            raise PermissionDenied
        return event

    def get_queryset(self):
        return CheckInList.objects.filter(event_id=self.kwargs['event_id'])

    def perform_create(self, serializer):
        event = self._get_event()
        # First list becomes default automatically
        is_first = not CheckInList.objects.filter(event=event).exists()
        serializer.save(event=event, is_default=is_first)


class CheckInListDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PUT / DELETE a single check-in list."""
    serializer_class = CheckInListSerializer
    permission_classes = [IsAuthenticated]
    queryset = CheckInList.objects.all()

    def get_object(self):
        obj = get_object_or_404(CheckInList, pk=self.kwargs['pk'])
        if not can_manage_event(obj.event, self.request.user):
            raise PermissionDenied
        return obj


class CheckInListAttendeesView(generics.ListAPIView):
    """Return all registrations for an event with their check-in status for a specific list."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, **kwargs):
        checkin_list = get_object_or_404(CheckInList, pk=pk)
        if not can_manage_event(checkin_list.event, request.user):
            raise PermissionDenied

        regs = (
            Registration.objects
            .filter(event=checkin_list.event)
            .exclude(status__in=[RegistrationStatusChoices.CANCELLED, RegistrationStatusChoices.REJECTED])
            .select_related('user')
            .prefetch_related('checkin_logs')
        )

        # Latest log entry per registration for this list
        log_map = {}
        for log in CheckInLog.objects.filter(checkin_list=checkin_list).select_related('scanned_by'):
            if log.registration_id not in log_map:
                log_map[log.registration_id] = log

        result = []
        for reg in regs:
            u = reg.user
            last_log = log_map.get(reg.id)
            result.append({
                'id': reg.id,
                'ticket_uuid': str(reg.ticket_uuid),
                'username': u.username,
                'full_name': f'{u.first_name} {u.last_name}'.strip() or u.username,
                'email': u.email,
                'status': reg.status,
                'is_checked_in': last_log.action == CheckInLog.ACTION_CHECK_IN if last_log else False,
                'checked_in_at': last_log.created_at if (last_log and last_log.action == CheckInLog.ACTION_CHECK_IN) else None,
                'scanned_by': last_log.scanned_by.username if (last_log and last_log.scanned_by) else None,
            })

        return Response(result)


class CheckInListCheckInView(generics.GenericAPIView):
    """POST ticket_uuid to check in (or undo) within a specific list."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, **kwargs):
        checkin_list = get_object_or_404(CheckInList, pk=pk)
        if not can_manage_event(checkin_list.event, request.user):
            raise PermissionDenied

        ticket_uuid = request.data.get('ticket_uuid')
        action_type = request.data.get('action', CheckInLog.ACTION_CHECK_IN)
        note = request.data.get('note', '')

        if not ticket_uuid:
            return Response({'error': 'ticket_uuid required'}, status=status.HTTP_400_BAD_REQUEST)

        reg = get_object_or_404(Registration, ticket_uuid=ticket_uuid, event=checkin_list.event)

        with transaction.atomic():
            log = CheckInLog.objects.create(
                checkin_list=checkin_list,
                registration=reg,
                action=action_type,
                scanned_by=request.user,
                note=note,
            )
            # Keep global is_checked_in in sync with the default list
            if checkin_list.is_default:
                reg.is_checked_in = (action_type == CheckInLog.ACTION_CHECK_IN)
                if reg.is_checked_in:
                    reg.checked_in_at = timezone.now()
                else:
                    reg.checked_in_at = None
                reg.save(update_fields=['is_checked_in', 'checked_in_at'])

        u = reg.user
        return Response({
            'message': 'Checked in' if action_type == CheckInLog.ACTION_CHECK_IN else 'Undone',
            'attendee': f'{u.first_name} {u.last_name}'.strip() or u.username,
            'action': action_type,
            'log_id': log.id,
        })


class EventCheckInLogsView(generics.ListAPIView):
    """GET recent check-in log entries for an event (organizer, newest first)."""
    serializer_class = CheckInLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # frontend expects a bare array; capped below

    def get_queryset(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            raise PermissionDenied
        return (
            CheckInLog.objects
            .filter(checkin_list__event=event)
            .select_related('checkin_list', 'registration__user', 'scanned_by')
        )[:200]
