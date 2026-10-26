"""Check-in lists: per-list attendee state, scanning, audit logs."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response

from common.choices import EventStatusChoices, PaymentStatusChoices, RegistrationStatusChoices
from common.permissions import can_check_in_event, can_manage_event

from ..models import INACTIVE_REGISTRATION_STATUSES, CheckInList, CheckInLog, Event, Registration
from ..serializers import CheckInListSerializer, CheckInLogSerializer


class EventCheckInListsView(generics.ListCreateAPIView):
    """GET list (check-in staff and managers) / POST create (managers)."""
    serializer_class = CheckInListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # lists are few; frontend expects a bare array

    def _get_event(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        allowed = (
            can_check_in_event(event, self.request.user)
            if self.request.method in SAFE_METHODS
            else can_manage_event(event, self.request.user)
        )
        if not allowed:
            raise PermissionDenied
        return event

    def get_queryset(self):
        return CheckInList.objects.filter(event=self._get_event())

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
        obj = get_object_or_404(CheckInList.objects.select_related('event'), pk=self.kwargs['pk'])
        allowed = (
            can_check_in_event(obj.event, self.request.user)
            if self.request.method in SAFE_METHODS
            else can_manage_event(obj.event, self.request.user)
        )
        if not allowed:
            raise PermissionDenied
        return obj


class CheckInListAttendeesView(generics.ListAPIView):
    """Return all registrations for an event with their check-in status for a specific list."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, **kwargs):
        checkin_list = get_object_or_404(CheckInList.objects.select_related('event'), pk=pk)
        if not can_check_in_event(checkin_list.event, request.user):
            raise PermissionDenied

        regs = (
            Registration.objects
            .filter(event=checkin_list.event)
            .exclude(status__in=INACTIVE_REGISTRATION_STATUSES)
            .select_related('user')
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
        checkin_list = get_object_or_404(CheckInList.objects.select_related('event'), pk=pk)
        if not can_check_in_event(checkin_list.event, request.user):
            raise PermissionDenied

        ticket_uuid = request.data.get('ticket_uuid')
        action_type = request.data.get('action', CheckInLog.ACTION_CHECK_IN)
        note = str(request.data.get('note', '') or '')[:200]

        if not ticket_uuid:
            return Response({'error': 'ticket_uuid required'}, status=status.HTTP_400_BAD_REQUEST)
        if action_type not in (CheckInLog.ACTION_CHECK_IN, CheckInLog.ACTION_UNDO):
            return Response({'error': 'action must be "check_in" or "undo".'}, status=status.HTTP_400_BAD_REQUEST)
        reg_lookup = Registration.objects.filter(ticket_uuid=ticket_uuid, event=checkin_list.event)
        try:
            reg_exists = reg_lookup.exists()
        except ValidationError:  # malformed UUID
            reg_exists = False
        if not reg_exists:
            return Response({'error': 'Ticket not found for this event.', 'status': 'invalid'},
                            status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            # Row lock: the same QR scanned at two gates at once is serialised.
            reg = (
                reg_lookup.select_for_update(of=('self',))
                .select_related('user', 'payment')
                .get()
            )
            last = (
                CheckInLog.objects.filter(checkin_list=checkin_list, registration=reg)
                .order_by('-created_at', '-id').values_list('action', flat=True).first()
            )
            is_in = last == CheckInLog.ACTION_CHECK_IN

            if action_type == CheckInLog.ACTION_CHECK_IN:
                error = self._entry_refused(reg, checkin_list.event)
                if error:
                    return Response({'error': error, 'status': 'invalid'}, status=status.HTTP_400_BAD_REQUEST)
                if is_in:
                    return Response({
                        'message': 'Ticket already checked in!',
                        'status': 'used',
                        'attendee': self._name(reg.user),
                        'action': action_type,
                    })
            elif not is_in:
                return Response({'error': 'This ticket is not checked in on this list.'},
                                status=status.HTTP_400_BAD_REQUEST)

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
                reg.checked_in_at = timezone.now() if reg.is_checked_in else None
                reg.save(update_fields=['is_checked_in', 'checked_in_at'])

        return Response({
            'message': 'Checked in' if action_type == CheckInLog.ACTION_CHECK_IN else 'Undone',
            'status': 'success',
            'attendee': self._name(reg.user),
            'action': action_type,
            'log_id': log.id,
        })

    @staticmethod
    def _name(user):
        return f'{user.first_name} {user.last_name}'.strip() or user.username

    @staticmethod
    def _entry_refused(reg, event):
        """Same rules as the main QR scanner (services.check_in_registration)."""
        if event.status == EventStatusChoices.CANCELLED:
            return 'This event was cancelled — entry must be refused.'
        if reg.status == RegistrationStatusChoices.PENDING:
            payment = getattr(reg, 'payment', None)
            if payment is not None and payment.status == PaymentStatusChoices.COMPLETED:
                reg.status = RegistrationStatusChoices.CONFIRMED
                reg.seat_held_until = None
                reg.save(update_fields=['status', 'seat_held_until'])
                return None
            return 'Ticket is NOT paid — registration is still pending payment.'
        if reg.status in INACTIVE_REGISTRATION_STATUSES:
            return 'Ticket is cancelled — entry must be refused.'
        return None


class EventCheckInLogsView(generics.ListAPIView):
    """GET recent check-in log entries for an event (staff, newest first)."""
    serializer_class = CheckInLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # frontend expects a bare array; capped below

    def get_queryset(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_check_in_event(event, self.request.user):
            raise PermissionDenied
        return (
            CheckInLog.objects
            .filter(checkin_list__event=event)
            .select_related('checkin_list', 'registration__user', 'scanned_by')
        )[:200]
